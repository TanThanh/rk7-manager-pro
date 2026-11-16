# web_bridge.py
import os
import sys
import json
import psutil
import time
import base64
import io
import hashlib
import getpass
import shutil
import threading
import subprocess
import webbrowser
import webview
import sqlite3
import uuid
import logging
from contextlib import closing
from PIL import Image
from pathlib import Path

logger = logging.getLogger("rk7_pro.web_bridge")

# Windows specific
try:
    import winshell
    import pythoncom
    WIN_ENV = True
except ImportError:
    WIN_ENV = False

from rk7_pro.core.models import ShortcutState
from rk7_pro.core.script_repository import ScriptRepository, ScriptSnippet
from rk7_pro.core.vault_files import VaultFiles
from rk7_pro.ucs_client import UcsClient, UcsUploadError
from rk7_pro.core.udb_checkview_service import UdbCheckViewService


class WebBridgeAPI:
    """JS Bridge exposed to webview via window.pywebview.api"""
    def __init__(self, settings_path=None, data_dir=None):
        self.base_dir = Path(data_dir).resolve() if data_dir else Path(__file__).parent.resolve()
        self.settings_path = Path(settings_path) if settings_path else self.base_dir / "settings.json"
        self.settings = self._load_settings()
        # pywebview recursively inspects public API attributes. Keep its Window
        # object private so native controls are not traversed during startup.
        self._window = None
        self._issue_panel = None
        self._issue_error = None
        self._ucs_selected_file = None
        self._ucs_client = None
        self._ucs_analysis = None
        self._checkview_service = UdbCheckViewService(self.base_dir / "rk7_pro" / "bin", data_dir=self.base_dir)
        self._checkview_data = None
        self._checkview_file = None
        # Paths
        target_dir = self.settings.get("shortcut_root") or str(Path.home() / "Desktop")
        if not Path(target_dir).exists():
            target_dir = str(Path.home() / "Desktop")
        self.shortcut_dir = Path(target_dir)
        self.card_backgrounds_dir = self.base_dir / "rk7_pro" / "card_backgrounds"
        self.favorites_file = self.base_dir / "rk7_pro" / "favorites.json"
        self.customization_file = self.base_dir / "rk7_pro" / "customization.json"
        self.launch_history_file = self.base_dir / "rk7_pro" / "launch_history.json"
        self.launch_history = self._load_launch_history()
        self._launch_history_lock = threading.Lock()
        self.activity_file = self.base_dir / "rk7_pro" / "activity.sqlite3"
        self._activity_lock = threading.Lock()
        self._init_activity()

        # Repositories
        self.states = {}
        vault_path = self.settings.get("script_vault_dir")
        if not vault_path or not Path(vault_path).exists():
            default_user_vault = Path.home() / "RK7_Script_Vault"
            if default_user_vault.exists():
                vault_path = str(default_user_vault)
            else:
                vault_path = str(self.base_dir / "vault")
        self.script_repo = ScriptRepository(vault_path)
        
        # Load shortcuts immediately on startup
        self.refresh_shortcuts()
        
        # Background worker
        self._tracking_active = True
        self._tracker_thread = None

    def set_window(self, window):
        self._window = window

    def set_issue_panel(self, panel):
        self._issue_panel = panel
        self._issue_error = None

    def set_issue_error(self, error):
        self._issue_error = str(error)

    def start_background_services(self):
        self.refresh_shortcuts()
        self._tracking_active = True
        self._tracker_thread = threading.Thread(target=self._process_tracker_loop, daemon=True)
        self._tracker_thread.start()

    def _load_settings(self):
        if self.settings_path.exists():
            try:
                with open(self.settings_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"shortcut_root": str(Path.home() / "Desktop"), "theme": "light"}

    def _save_settings(self):
        try:
            with open(self.settings_path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
            return True
        except Exception as e:
            print("Failed to save settings:", e)
            return False

    def _load_favorites(self):
        if self.favorites_file.exists():
            try:
                with open(self.favorites_file, 'r', encoding='utf-8') as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_favorites(self, favs_set):
        try:
            with open(self.favorites_file, 'w', encoding='utf-8') as f:
                json.dump(list(favs_set), f)
        except Exception as e:
            print("Failed to save favorites:", e)

    def _load_customizations(self):
        if self.customization_file.exists():
            try:
                with open(self.customization_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_customizations(self, data):
        try:
            with open(self.customization_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print("Failed to save customizations:", e)
            return False

    def _load_launch_history(self):
        try:
            with open(self.launch_history_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_launch_history(self):
        try:
            temp_path = self.launch_history_file.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.launch_history, f, indent=2)
            os.replace(temp_path, self.launch_history_file)
        except OSError as exc:
            print("Failed to save launch history:", exc)

    def _init_activity(self):
        self.activity_file.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.activity_file)) as db:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS events (event_id TEXT PRIMARY KEY, shortcut_id TEXT NOT NULL, event_type TEXT NOT NULL, timestamp REAL NOT NULL, process_id INTEGER, target_path TEXT, result TEXT, error_message TEXT)")
                db.execute("CREATE INDEX IF NOT EXISTS events_shortcut_time ON events(shortcut_id, timestamp DESC)")

    def _log_event(self, shortcut_id, event_type, process_id=None, result=None, error_message=None):
        state = self.states.get(shortcut_id)
        if not hasattr(self, "activity_file"):
            return
        with self._activity_lock, closing(sqlite3.connect(self.activity_file)) as db:
            with db:
                db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (uuid.uuid4().hex, shortcut_id, event_type, time.time(), process_id,
                            state.target_exe_path if state else None, result, error_message))

    def get_activity(self, shortcut_id, date=None):
        if shortcut_id not in self.states:
            return []
        query = "SELECT event_id, shortcut_id, event_type, timestamp, process_id, target_path, result, error_message FROM events WHERE shortcut_id = ?"
        params = [shortcut_id]
        if date:
            try:
                from datetime import datetime, timedelta
                start = datetime.strptime(date, "%Y-%m-%d").timestamp()
                query += " AND timestamp >= ? AND timestamp < ?"
                params.extend((start, start + timedelta(days=1).total_seconds()))
            except ValueError:
                return []
        with closing(sqlite3.connect(self.activity_file)) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(query + " ORDER BY timestamp DESC LIMIT 200", params)]

    @staticmethod
    def _background_data(path):
        if not path or not Path(path).is_file():
            return None
        try:
            suffix = Path(path).suffix.lower()
            mime = "jpeg" if suffix in (".jpg", ".jpeg") else suffix.lstrip(".")
            with open(path, "rb") as f:
                return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode('ascii')}"
        except OSError:
            return None

    # ------------------ JS API Methods ------------------

    def ucs_get_cached_state(self):
        """Return the current active UCS analysis and selected file info if already loaded in this session."""
        has_analysis = self._ucs_analysis is not None and self._ucs_client is not None
        file_info = None
        if self._ucs_selected_file and self._ucs_selected_file.is_file():
            file_info = {
                "path": str(self._ucs_selected_file),
                "filename": self._ucs_selected_file.name,
                "size": self._ucs_selected_file.stat().st_size
            }
        recent_files = self.settings.get("ucs_recent_files", [])
        # Filter existing files
        valid_recent = []
        for f in recent_files:
            try:
                p = Path(f.get("path", ""))
                if p.is_file():
                    valid_recent.append(f)
            except Exception:
                pass
        return {
            "has_analysis": has_analysis,
            "analysis": self._ucs_analysis if has_analysis else None,
            "selected_file": file_info,
            "recent_files": valid_recent[:5]
        }

    def ucs_select_file_path(self, file_path):
        """Set the selected UDB file from a known file path (e.g. from recent list)."""
        if not file_path:
            return {"success": False, "error": "Path cannot be empty."}
        p = Path(file_path).resolve()
        if not p.is_file() or p.suffix.lower() != ".udb":
            return {"success": False, "error": "UDB file does not exist or invalid format."}
        self._ucs_selected_file = p
        return {"success": True, "filename": p.name, "path": str(p), "size": p.stat().st_size}

    def ucs_select_file(self):
        if self._window is None:
            return {"success": False, "error": "Window is not ready."}
        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("UDB database (*.udb)",))
        if not selected:
            return {"success": False, "cancelled": True}
        path = Path(selected[0])
        if not path.is_file() or path.suffix.lower() != ".udb":
            return {"success": False, "error": "Choose an existing .udb file."}
        self._ucs_selected_file = path
        return {"success": True, "filename": path.name, "path": str(path), "size": path.stat().st_size}

    def ucs_get_account(self):
        account = self.settings.get("ucs_account", {})
        return {
            "has_saved": bool(account.get("username") and account.get("password")),
            "username": account.get("username", ""),
            "password": account.get("password", "")
        }

    def ucs_save_account(self, username, password):
        self.settings["ucs_account"] = {
            "username": username.strip(),
            "password": password
        }
        self._save_settings()
        return {"success": True}

    def ucs_login(self, username, password, remember=True):
        user = (username or "").strip()
        pwd = password or ""
        if not user or not pwd:
            return {"success": False, "error": "Enter your UCS username and password."}
        client = UcsClient()
        try:
            client.verify_credentials(user, pwd)
            if remember:
                self.settings["ucs_account"] = {
                    "username": user,
                    "password": pwd
                }
            elif "ucs_account" in self.settings:
                del self.settings["ucs_account"]
            self._save_settings()
            return {"success": True, "username": user}
        except UcsUploadError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            return {"success": False, "error": f"Connection error: {exc}"}
        finally:
            client.close()

    def ucs_clear_account(self):
        if "ucs_account" in self.settings:
            del self.settings["ucs_account"]
            self._save_settings()
        return {"success": True}

    def ucs_upload_and_analyze(self, username=None, password=None):
        if self._ucs_selected_file is None:
            return {"success": False, "error": "Choose a .udb file first."}
        
        # Use provided or saved credentials
        settings = getattr(self, "settings", None)
        saved_account = settings.get("ucs_account", {}) if isinstance(settings, dict) else {}
        final_username = (username or "").strip() or saved_account.get("username", "")
        final_password = password or saved_account.get("password", "")

        if not final_username or not final_password:
            return {"success": False, "error": "Enter your UCS username and password or sign in first."}

        if self._ucs_client is not None:
            self._ucs_client.close()
        self._ucs_client = UcsClient()
        self._ucs_analysis = None
        try:
            result = self._ucs_client.upload_and_analyze(self._ucs_selected_file, final_username, final_password,
                                                         fetch_tables=False)
            self._ucs_analysis = result
            # Automatically persist credentials upon successful analysis if not already saved or if updated
            if isinstance(settings, dict):
                if final_username and final_password:
                    settings["ucs_account"] = {
                        "username": final_username,
                        "password": final_password
                    }
                # Record recent file
                if self._ucs_selected_file and self._ucs_selected_file.is_file():
                    recent = settings.get("ucs_recent_files", [])
                    p_str = str(self._ucs_selected_file)
                    recent = [r for r in recent if r.get("path") != p_str]
                    recent.insert(0, {
                        "path": p_str,
                        "filename": self._ucs_selected_file.name,
                        "size": self._ucs_selected_file.stat().st_size,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S")
                    })
                    settings["ucs_recent_files"] = recent[:10]
                if hasattr(self, "_save_settings"):
                    self._save_settings()
            return {"success": True, "analysis": result, "username": final_username, "password": final_password}
        except UcsUploadError as exc:
            self._ucs_client.close()
            self._ucs_client = None
            return {"success": False, "error": str(exc)}

    def ucs_read_table(self, name):
        if self._ucs_client is None:
            return {"success": False, "error": "Upload a UDB file first."}
        summary = next((table for table in self._ucs_analysis.get("tables", [])
                        if table["name"] == name), None) if self._ucs_analysis else None
        if summary is None:
            return {"success": False, "error": "This table is not in the UCS DB-info result."}
        client = self._ucs_client.fork_for_table_reads()
        try:
            return {"success": True, "table": client.fetch_table_summary(name, summary["rows"])}
        except UcsUploadError as exc:
            return {"success": False, "error": str(exc)}
        finally:
            client.close()

    def ucs_get_operation_codes(self):
        candidates = [
            self.base_dir / "rk7_pro" / "operation_codes.json",
            self.base_dir / "web_ui" / "operation_codes.json"
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "rk7_pro" / "operation_codes.json")
            candidates.append(Path(sys._MEIPASS) / "web_ui" / "operation_codes.json")
        for json_file in candidates:
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def ucs_get_operationlog_fields(self):
        candidates = [
            self.base_dir / "rk7_pro" / "operationlog_fields.json",
            self.base_dir / "web_ui" / "operationlog_fields.json"
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "rk7_pro" / "operationlog_fields.json")
            candidates.append(Path(sys._MEIPASS) / "web_ui" / "operationlog_fields.json")
        for json_file in candidates:
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def ucs_get_printchecks_fields(self):
        candidates = [
            self.base_dir / "rk7_pro" / "printchecks_fields.json",
            self.base_dir / "web_ui" / "printchecks_fields.json"
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "rk7_pro" / "printchecks_fields.json")
            candidates.append(Path(sys._MEIPASS) / "web_ui" / "printchecks_fields.json")
        for json_file in candidates:
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    def ucs_get_udb_dictionary(self):
        candidates = [
            self.base_dir / "rk7_pro" / "rk7_udb_dictionary.json",
            self.base_dir / "web_ui" / "rk7_udb_dictionary.json"
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.append(Path(sys._MEIPASS) / "rk7_pro" / "rk7_udb_dictionary.json")
            candidates.append(Path(sys._MEIPASS) / "web_ui" / "rk7_udb_dictionary.json")
        for json_file in candidates:
            if json_file.exists():
                try:
                    with open(json_file, "r", encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass
        return {}

    # ------------------ UCS CHECKVIEW METHODS ------------------
    def checkview_select_file(self):
        """Open file dialog to pick a .udb file for CheckView."""
        if self._window is None:
            return {"success": False, "error": "Window is not ready."}
        selected = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("UDB database (*.udb)",))
        if not selected:
            return {"success": False, "cancelled": True}
        path = Path(selected[0])
        if not path.is_file() or path.suffix.lower() != ".udb":
            return {"success": False, "error": "Vui lòng chọn file .udb hợp lệ."}
        return self.checkview_load_file(str(path))

    def checkview_load_file(self, file_path):
        """Parse the given UDB file and return summary header and checks list."""
        if not file_path:
            return {"success": False, "error": "Đường dẫn file không được để trống."}
        path = Path(file_path).resolve()
        if not path.is_file() or path.suffix.lower() != ".udb":
            return {"success": False, "error": f"Không tìm thấy file: {file_path}"}
        try:
            parsed = self._checkview_service.parse_udb_database(str(path))
            self._checkview_data = parsed
            self._checkview_file = path
            # Don't send large _raw_tables to JS
            result = {
                "success": True,
                "filename": parsed.get("filename"),
                "path": str(path),
                "header": parsed.get("header"),
                "checks": parsed.get("checks")
            }
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_get_detail(self, visit_id, check_uni=None):
        """Get full receipt POS view and audit logs for a visit."""
        if not self._checkview_data:
            return {"success": False, "error": "Chưa tải dữ liệu UDB."}
        try:
            return self._checkview_service.get_check_view_detail(self._checkview_data, str(visit_id), check_uni)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_get_shift_report(self, shift_num=None):
        """Build cashier shift handover report (FO.201) from loaded UDB data."""
        if not self._checkview_data:
            return {"success": False, "error": "Chưa tải dữ liệu UDB."}
        try:
            return self._checkview_service.get_shift_handover_report(self._checkview_data, shift_num=shift_num)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_export_receipt_pdf(self, visit_id, check_uni, image_data):
        """Save the exact receipt preview image as an 80 mm PDF."""
        if not self._window or not self._checkview_data:
            return {"success": False, "error": "Chưa có hóa đơn để xuất."}
        check = next((c for c in self._checkview_data.get("checks", [])
                      if str(c.get("visit_id")) == str(visit_id) and str(c.get("check_uni")) == str(check_uni)), None)
        if check is None:
            return {"success": False, "error": "Hóa đơn không thuộc file UDB hiện tại."}
        try:
            if not isinstance(image_data, str) or not image_data.startswith("data:image/png;base64,"):
                raise ValueError("Dữ liệu xem trước không hợp lệ.")
            raw = base64.b64decode(image_data.split(",", 1)[1], validate=True)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError("Phiếu quá dài để xuất PDF.")
            with Image.open(io.BytesIO(raw)) as source:
                source.load()
                if source.width != 640 or source.height < 100 or source.height > 30000:
                    raise ValueError("Kích thước phiếu không hợp lệ.")
                receipt = source.convert("RGB")
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"Ban-sao-check-{check['check_num']}.pdf",
                file_types=("PDF document (*.pdf)",),
            )
            if not selected:
                return {"success": False, "cancelled": True}
            target = Path(selected[0]).with_suffix(".pdf")
            receipt.save(target, "PDF", resolution=203.2, title="Ban sao hoa don CheckView")
            return {"success": True, "path": str(target)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_export_receipt_xml(self, visit_id, check_uni):
        """Save the selected UDB check as structured XML."""
        if not self._window or not self._checkview_data:
            return {"success": False, "error": "Chưa có hóa đơn để xuất."}
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            rest_id = self._checkview_data.get("header", {}).get("restaurant")
            master = self._checkview_service.ref_service.get_master_data_for_restaurant(rest_id)
            if not InvoiceXmlTemplateService.supports(self._checkview_data, master):
                return {
                    "success": False,
                    "error": f"Nhà hàng #{rest_id} chưa có mẫu template XML trong thư mục invoice_templates (hoặc sai gói Master Data)."
                }
            xml_bytes = InvoiceXmlTemplateService.build(self._checkview_data, master, visit_id, check_uni)
            check = next(c for c in self._checkview_data["checks"]
                         if str(c.get("visit_id")) == str(visit_id) and str(c.get("check_uni")) == str(check_uni))
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"Check-{check['check_num']}-{self._checkview_file.stem if self._checkview_file else 'UDB'}.xml",
                file_types=("XML document (*.xml)",),
            )
            if not selected:
                return {"success": False, "cancelled": True}
            target = Path(selected[0]).with_suffix(".xml")
            target.write_bytes(xml_bytes)
            return {"success": True, "path": str(target)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_export_batch_xml(self, items):
        """Export multiple UDB checks into a single XML file (matching invoice.xml / invoice_rk.xml format)."""
        if not self._window or not self._checkview_data:
            return {"success": False, "error": "Chưa có dữ liệu hóa đơn để xuất."}
        if not items:
            return {"success": False, "error": "Chưa chọn hóa đơn nào để xuất."}
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            rest_id = self._checkview_data.get("header", {}).get("restaurant")
            master = self._checkview_service.ref_service.get_master_data_for_restaurant(rest_id)
            if not InvoiceXmlTemplateService.supports(self._checkview_data, master):
                return {
                    "success": False,
                    "error": f"Nhà hàng #{rest_id} chưa có mẫu template XML trong thư mục invoice_templates (hoặc sai gói Master Data)."
                }
            
            # Sort items by PrintNumber (1 -> N) based on check metadata in self._checkview_data
            check_map = {
                (str(c.get("visit_id", "")), str(c.get("check_uni", ""))): c
                for c in self._checkview_data.get("checks", [])
            }
            def get_sort_key(it):
                v_id = str(it.get("visit_id", ""))
                c_uni = str(it.get("check_uni", ""))
                c_info = check_map.get((v_id, c_uni), {})
                p_num = c_info.get("print_num")
                try:
                    return (0, int(p_num)) if p_num is not None and str(p_num).isdigit() else (1, str(p_num))
                except Exception:
                    return (2, 0)

            sorted_items = sorted(items, key=get_sort_key)

            receipt_blocks = []
            exported_count = 0
            for it in sorted_items:
                v_id = str(it.get("visit_id", ""))
                c_uni = str(it.get("check_uni", ""))
                try:
                    xml_b = InvoiceXmlTemplateService.build(self._checkview_data, master, v_id, c_uni)
                    xml_str = xml_b.decode("utf-8").strip()
                    if xml_str.startswith("<?xml"):
                        xml_str = xml_str.split("?>", 1)[1].strip()
                    receipt_blocks.append(xml_str)
                    exported_count += 1
                except Exception as ex:
                    logger.debug("Failed to build check visit=%s uni=%s: %s", v_id, c_uni, ex)

            if not receipt_blocks:
                return {"success": False, "error": "Không có hóa đơn nào hợp lệ để xuất (có thể do các check đang mở hoặc đã hủy)."}

            combined_xml = "\n".join(receipt_blocks) + "\n"
            default_name = f"Invoices-{self._checkview_file.stem if self._checkview_file else 'UDB'}-{exported_count}checks.xml"
            selected = self._window.create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=default_name,
                file_types=("XML document (*.xml)",),
            )
            if not selected:
                return {"success": False, "cancelled": True}
            target = Path(selected[0]).with_suffix(".xml")
            target.write_text(combined_xml, encoding="utf-8")
            return {"success": True, "path": str(target), "count": exported_count}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_get_state(self):
        """Get current loaded CheckView state."""
        if not self._checkview_data:
            return {"has_data": False}
        return {
            "has_data": True,
            "filename": self._checkview_data.get("filename"),
            "path": str(self._checkview_file) if self._checkview_file else "",
            "header": self._checkview_data.get("header"),
            "checks": self._checkview_data.get("checks")
        }

    def checkview_update_employee(self, emp_id, name):
        """Update and save employee display name."""
        success = self._checkview_service.save_employee_name(emp_id, name)
        return {"success": success}

    def checkview_get_employees(self):
        """Get current employee directory map."""
        return self._checkview_service._employee_map

    def checkview_list_master_packages(self):
        """List all loaded Master Data packages."""
        return self._checkview_service.ref_service.list_packages()

    def checkview_get_master_package_data(self, package_id):
        """Get full data of a master data package for Master Data explorer."""
        try:
            data = self._checkview_service.ref_service.get_package_data(package_id)
            if data is None:
                return {"success": False, "error": f"Không tìm thấy gói {package_id}"}
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_rename_master_package(self, package_id, display_name, new_package_id=None):
        """Change a package's visible name and optionally update its ID."""
        try:
            return self._checkview_service.ref_service.rename_package(package_id, display_name, new_package_id)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_delete_master_package(self, package_id):
        """Delete a package and its mappings."""
        try:
            return self._checkview_service.ref_service.delete_package(package_id)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def checkview_import_master_package(self, target_package_id=None, display_name=None, overwrite=False):
        """Pick a refsdata.udb file and extract to JSON Master package.
        If target_package_id is specified or overwrite=True, update existing package instead of creating master_2, master_3...
        """
        if not self._window:
            return {"success": False, "error": "Cửa sổ chưa sẵn sàng"}
        try:
            # pywebview file-filter descriptions accept letters, digits, spaces,
            # and underscores only; a hyphen raises before the picker opens.
            file_types = ("RK7 Master Data (*.udb;*.db)", "All files (*.*)")
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=file_types
            )
            if not result or len(result) == 0:
                return {"success": False, "cancelled": True}
            
            file_path = result[0]
            extract_res = self._checkview_service.ref_service.extract_refsdata_to_json(
                Path(file_path),
                package_id=target_package_id,
                display_name=display_name,
                overwrite=overwrite
            )
            return extract_res
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # SQL MASTER SYNC METHODS
    # ==========================================

    def sql_list_connections(self):
        """Get all saved SQL connection profiles."""
        try:
            from rk7_pro.core.sql_master_sync_service import SqlMasterSyncService
            return {"success": True, "connections": SqlMasterSyncService.load_connections()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sql_save_connection(self, profile):
        """Add or update an SQL connection profile."""
        try:
            from rk7_pro.core.sql_master_sync_service import SqlMasterSyncService
            import uuid
            connections = SqlMasterSyncService.load_connections()
            prof_id = profile.get("id")
            if not prof_id:
                profile["id"] = f"sql_{uuid.uuid4().hex[:8]}"
                connections.append(profile)
            else:
                idx = next((i for i, c in enumerate(connections) if c.get("id") == prof_id), -1)
                if idx >= 0:
                    connections[idx] = profile
                else:
                    connections.append(profile)
            SqlMasterSyncService.save_connections(connections)
            return {"success": True, "connections": connections, "profile": profile}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sql_delete_connection(self, profile_id):
        """Delete an SQL connection profile."""
        try:
            from rk7_pro.core.sql_master_sync_service import SqlMasterSyncService
            connections = SqlMasterSyncService.load_connections()
            connections = [c for c in connections if c.get("id") != profile_id]
            SqlMasterSyncService.save_connections(connections)
            return {"success": True, "connections": connections}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sql_test_connection(self, profile):
        """Test read-only connection to SQL Server without saving."""
        try:
            from rk7_pro.core.sql_master_sync_service import SqlMasterSyncService
            return SqlMasterSyncService.test_connection(profile)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def sql_sync_connection(self, profile_id):
        """Run safe NOLOCK queries to fetch master data and compile master.json with live progress."""
        try:
            from rk7_pro.core.sql_master_sync_service import SqlMasterSyncService

            def on_progress(step, total, table, status, message, count=None):
                if self._window:
                    payload = json.dumps({
                        "step": step,
                        "total": total,
                        "table": table,
                        "status": status,
                        "message": message,
                        "count": count
                    }, ensure_ascii=False)
                    try:
                        self._window.evaluate_js(f"if (window.onMasterApiSyncProgress) window.onMasterApiSyncProgress({payload});")
                    except Exception:
                        pass

            return SqlMasterSyncService.sync_master_data(profile_id, progress_callback=on_progress)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # RK7 XML API MASTER SYNC METHODS
    # ==========================================

    def api_list_connections(self):
        """Get all saved RK7 API connection profiles."""
        try:
            from rk7_pro.core.rk7_api_sync_service import Rk7ApiSyncService
            return {"success": True, "connections": Rk7ApiSyncService.load_connections()}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_save_connection(self, profile):
        """Add or update an RK7 API connection profile."""
        try:
            from rk7_pro.core.rk7_api_sync_service import Rk7ApiSyncService
            import uuid
            if not profile.get("user"):
                profile["user"] = "httpapi"
            if not profile.get("password"):
                profile["password"] = "1"
            if profile.get("url"):
                profile["url"] = Rk7ApiSyncService.normalize_url(profile["url"])

            connections = Rk7ApiSyncService.load_connections()
            prof_id = profile.get("id")
            if not prof_id:
                profile["id"] = f"api_{uuid.uuid4().hex[:8]}"
                connections.append(profile)
            else:
                idx = next((i for i, c in enumerate(connections) if c.get("id") == prof_id), -1)
                if idx >= 0:
                    connections[idx] = profile
                else:
                    connections.append(profile)
            Rk7ApiSyncService.save_connections(connections)
            return {"success": True, "connections": connections, "profile": profile}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_delete_connection(self, profile_id):
        """Delete an RK7 API connection profile."""
        try:
            from rk7_pro.core.rk7_api_sync_service import Rk7ApiSyncService
            connections = Rk7ApiSyncService.load_connections()
            connections = [c for c in connections if c.get("id") != profile_id]
            Rk7ApiSyncService.save_connections(connections)
            return {"success": True, "connections": connections}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_test_connection(self, profile):
        """Test read-only connection to RK7 API without saving."""
        try:
            from rk7_pro.core.rk7_api_sync_service import Rk7ApiSyncService
            return Rk7ApiSyncService.test_connection(profile)
        except Exception as e:
            return {"success": False, "error": str(e)}

    def api_sync_connection(self, profile_id):
        """Fetch master data from RK7 XML API and compile master json package with live progress."""
        try:
            from rk7_pro.core.rk7_api_sync_service import Rk7ApiSyncService

            def on_progress(step, total, table, status, message, count=None):
                if self._window:
                    payload = json.dumps({
                        "step": step,
                        "total": total,
                        "table": table,
                        "status": status,
                        "message": message,
                        "count": count
                    }, ensure_ascii=False)
                    try:
                        self._window.evaluate_js(f"if (window.onMasterApiSyncProgress) window.onMasterApiSyncProgress({payload});")
                    except Exception:
                        pass

            return Rk7ApiSyncService.sync_master_data(profile_id, progress_callback=on_progress)
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==========================================
    # XML TEMPLATE MANAGEMENT METHODS
    # ==========================================

    def template_list_all(self):
        """List all XML templates from invoice_templates directory."""
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            templates = InvoiceXmlTemplateService.list_templates()
            return {"success": True, "templates": templates}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def template_get_detail(self, template_id):
        """Read full JSON content of a template file."""
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            templates = InvoiceXmlTemplateService.list_templates()
            target = next((t for t in templates if t.get("id") == template_id), None)
            if not target:
                return {"success": False, "error": f"Không tìm thấy template {template_id}"}
            file_path = Path(target.get("_file_path"))
            raw_json = file_path.read_text(encoding="utf-8")
            return {"success": True, "template": target, "raw_json": raw_json}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def template_save(self, template_id, raw_json_str):
        """Save/update template JSON file."""
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            # Validate JSON
            parsed = json.loads(raw_json_str)
            target_id = parsed.get("id") or template_id
            if not target_id:
                raise ValueError("Template cần có trường 'id' hợp lệ.")
            templates_dir = InvoiceXmlTemplateService.get_templates_dir()
            file_path = templates_dir / f"{target_id}.json"
            templates_dir.mkdir(parents=True, exist_ok=True)
            file_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
            return {"success": True, "template": parsed}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def template_delete(self, template_id):
        """Delete template JSON file."""
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            templates = InvoiceXmlTemplateService.list_templates()
            target = next((t for t in templates if t.get("id") == template_id), None)
            if not target:
                return {"success": False, "error": f"Không tìm thấy template {template_id}"}
            file_path = Path(target.get("_file_path"))
            if file_path.is_file():
                file_path.unlink()
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def template_import_from_xml(self):
        """Open a file dialog to select an XML file, analyze it, and return the generated template JSON."""
        if not self._window:
            return {"success": False, "error": "Cửa sổ chưa sẵn sàng."}
        try:
            from rk7_pro.core.invoice_xml_template_service import InvoiceXmlTemplateService
            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=("XML files (*.xml;*.txt)", "All files (*.*)"),
            )
            if not selected:
                return {"success": False, "cancelled": True}
            xml_path = Path(selected[0])
            tpl = InvoiceXmlTemplateService.generate_template_from_xml(xml_path)
            return {
                "success": True,
                "filename": xml_path.name,
                "path": str(xml_path),
                "template": tpl,
                "raw_json": json.dumps(tpl, indent=2, ensure_ascii=False)
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


    def open_issue_workspace(self):
        """Show the remote issue view beside the existing app sidebar."""
        try:
            if self._issue_panel is None:
                return {"success": False, "error": self._issue_error or "Issue view is still loading."}
            self._issue_panel.set_visible(True)
            return {"success": True}
        except Exception as exc:
            print("Failed to open Issue Workspace:", exc)
            return {"success": False, "error": str(exc)}

    def get_issue_workspace_status(self):
        if self._issue_panel is None:
            return {"state": "error" if self._issue_error else "loading", "error": self._issue_error}
        return self._issue_panel.get_status()

    def hide_issue_workspace(self):
        if self._issue_panel is not None:
            self._issue_panel.set_visible(False)
        return {"success": True}

    def open_issue_in_browser(self):
        """Open the issue workspace when the remote site disallows embedding."""
        return webbrowser.open("https://ghiissue.itspecialone.site/")


    # ------------------ AUTHENTICATION & RBAC ------------------
    def auth_get_saved_credentials(self):
        """Retrieve remembered user credentials from settings."""
        creds = self.settings.get("auth_saved_credentials", {})
        if creds and creds.get("username") and creds.get("password"):
            return {
                "has_saved": True,
                "username": creds.get("username", ""),
                "password": creds.get("password", ""),
                "remember": bool(creds.get("remember", True))
            }
        return {"has_saved": False, "username": "", "password": "", "remember": False}

    def auth_clear_saved_credentials(self):
        """Clear remembered user credentials."""
        if "auth_saved_credentials" in self.settings:
            del self.settings["auth_saved_credentials"]
            self._save_settings()
        return {"success": True}

    def auth_login(self, username, password, remember=True):
        """Authenticate user against auth_users.json and return role & permissions."""
        try:
            users_file = self.base_dir / "auth_users.json"
            if not users_file.is_file() and getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                meipass_users = Path(sys._MEIPASS) / "auth_users.json"
                if meipass_users.is_file():
                    users_file = meipass_users
            if not users_file.is_file():
                # Default users if not created
                default_users = [
                    {"username": "admin", "password": "123", "role": "admin", "display_name": "Administrator", "allowed_tabs": ["shortcuts", "vault", "issues", "checkview", "sql-sync", "settings"]},
                    {"username": "rk7", "password": "rk7", "role": "checkview_only", "display_name": "RK7 Checkview Operator", "allowed_tabs": ["checkview", "sql-sync"]}
                ]
                users_file.write_text(json.dumps(default_users, indent=2), encoding="utf-8")
                users = default_users
            else:
                users = json.loads(users_file.read_text(encoding="utf-8"))

            user = next((u for u in users if u.get("username") == username and u.get("password") == password), None)
            if not user:
                return {"success": False, "error": "Tên đăng nhập hoặc mật khẩu không chính xác."}

            if remember:
                self.settings["auth_saved_credentials"] = {
                    "username": username,
                    "password": password,
                    "remember": True
                }
            else:
                if "auth_saved_credentials" in self.settings:
                    del self.settings["auth_saved_credentials"]
            self._save_settings()

            return {
                "success": True,
                "user": {
                    "username": user.get("username"),
                    "display_name": user.get("display_name") or user.get("username"),
                    "role": user.get("role", "user"),
                    "allowed_tabs": user.get("allowed_tabs", ["checkview"])
                }
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_initial_data(self):
        """Called by Javascript on load."""
        return {
            "settings": self.settings,
            "shortcuts": self.get_shortcuts(),
            "stats": self.get_stats(),
            "local_user": getpass.getuser(),
        }

    def get_shortcuts(self):
        """Return array of shortcut objects."""
        items = []
        for s in self.states.values():
            bg_data = self._background_data(s.custom_background)
            launch_data = self.launch_history.get(s.id, {})

            items.append({
                "id": s.id,
                "name": s.name,
                "is_pinned": s.is_pinned,
                "is_running": s.is_running,
                "working_directory": s.working_directory,
                "target_exe_path": s.target_exe_path,
                "arguments": s.arguments or "",
                "shortcut_path": str(self.shortcut_dir / s.id),
                "file_modified": (self.shortcut_dir / s.id).stat().st_mtime if (self.shortcut_dir / s.id).exists() else None,
                "status": self._shortcut_status(s),
                "process_id": s.process_id if s.is_running else None,
                "category": self._load_customizations().get(s.id, {}).get("category", ""),
                "notes": self._load_customizations().get(s.id, {}).get("notes", ""),
                "launch_count": launch_data.get("count", 0),
                "last_launched": launch_data.get("last_launched"),
                "custom_name": s.custom_name,
                "custom_color": s.custom_color,
                "custom_icon": s.custom_icon,
                "custom_background": bg_data,
                "display_name": s.custom_name if s.custom_name else s.name
            })
        items.sort(key=lambda x: (not x["is_pinned"], x["display_name"].lower()))
        return items

    def _shortcut_status(self, state):
        if not (self.shortcut_dir / state.id).exists():
            return "Missing Path"
        if state.target_exe_path and not Path(state.target_exe_path).exists():
            return "Missing Path"
        if state.is_running and state.process_id:
            return "Running"
        if state.tracking_mode == "error":
            return "Error"
        return "Ready" if state.target_exe_path else "Unknown"

    def save_shortcut_metadata(self, shortcut_id, changes):
        state = self.states.get(shortcut_id)
        if not state:
            return {"success": False, "error": "Shortcut not found"}
        allowed = {"name", "category", "notes"}
        if not isinstance(changes, dict) or set(changes) - allowed:
            return {"success": False, "error": "Unsupported metadata field"}
        customs = self._load_customizations()
        record = customs.setdefault(shortcut_id, {})
        for key, value in changes.items():
            if not isinstance(value, str) or len(value) > 2000:
                return {"success": False, "error": "Invalid value"}
            record[key] = value.strip()
        if not self._save_customizations(customs):
            return {"success": False, "error": "Could not save metadata"}
        state.custom_name = record.get("name") or None
        self._log_event(shortcut_id, "Configuration Updated", result="Saved internal metadata")
        return {"success": True}

    def get_stats(self):
        total = len(self.states)
        running = sum(1 for s in self.states.values() if s.is_running)
        pinned = sum(1 for s in self.states.values() if s.is_pinned)
        return {
            "total": total,
            "running": running,
            "pinned": pinned
        }

    def refresh_shortcuts(self):
        """Scan directory and reload states."""
        favorites = self._load_favorites()
        customs = self._load_customizations()
        new_states = {}

        if not self.shortcut_dir.exists():
            self.states = {}
            return self.get_shortcuts()

        files = [f.name for f in self.shortcut_dir.iterdir() if f.suffix.lower() == '.lnk']
        
        has_com = False
        if WIN_ENV:
            try:
                pythoncom.CoInitialize()
                has_com = True
            except Exception:
                pass

        for filename in files:
            state = None
            if WIN_ENV and has_com:
                try:
                    link_path = self.shortcut_dir / filename
                    info = winshell.shortcut(str(link_path))
                    state = ShortcutState(
                        id=filename,
                        name=filename.replace('.lnk', ''),
                        is_pinned=(filename in favorites),
                        target_exe_path=str(info.path),
                        working_directory=str(info.working_directory) if info.working_directory else str(Path(info.path).parent),
                        arguments=str(info.arguments) if info.arguments else ""
                    )
                except Exception:
                    pass

            if not state:
                state = ShortcutState(
                    id=filename,
                    name=filename.replace('.lnk', ''),
                    is_pinned=(filename in favorites)
                )

            # Preserve existing running state if same id
            if filename in self.states:
                state.is_running = self.states[filename].is_running
                state.process_id = self.states[filename].process_id
                state.tracking_mode = self.states[filename].tracking_mode

            if filename in customs:
                c = customs[filename]
                state.custom_name = c.get("name")
                state.custom_color = c.get("color")
                state.custom_icon = c.get("icon")
                bg = c.get("background")
                if bg:
                    p = self.base_dir / "rk7_pro" / bg
                    state.custom_background = str(p) if p.exists() else None

            new_states[filename] = state

        self.states = new_states
        return self.get_shortcuts()

    def launch_shortcut(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state:
            return {"success": False, "error": "Shortcut not found"}

        self._log_event(shortcut_id, "Launch Requested", result="Requested by user")

        try:
            exe_path = state.target_exe_path
            args = state.arguments
            cwd = state.working_directory

            if exe_path and Path(exe_path).exists() and Path(exe_path).is_file():
                cmd = f'"{exe_path}" {args}' if args else f'"{exe_path}"'
                creationflags = 0x00000008 | 0x00000200
                process = subprocess.Popen(
                    cmd,
                    cwd=cwd if cwd and Path(cwd).exists() else None,
                    shell=False,
                    creationflags=creationflags,
                    close_fds=True
                )
                state.is_running = True
                state.process_id = process.pid
                state.tracking_mode = "pid"
                self._log_event(shortcut_id, "Launch Successful", process_id=process.pid, result="Process created")
            else:
                link_path = self.shortcut_dir / shortcut_id
                os.startfile(str(link_path))
                state.is_running = False
                state.process_id = None
                state.tracking_mode = "unknown"
                self._log_event(shortcut_id, "Launch Requested", result="Accepted by Windows; process unverified")

            self._broadcast_state_change(state)
            with self._launch_history_lock:
                launch_data = self.launch_history.setdefault(shortcut_id, {"count": 0})
                launch_data["count"] = int(launch_data.get("count", 0)) + 1
                launch_data["last_launched"] = time.time()
                self._save_launch_history()
                return {"success": True, "process_id": state.process_id, "launch_count": launch_data["count"],
                        "last_launched": launch_data["last_launched"]}
        except Exception as e:
            state.tracking_mode = "error"
            self._log_event(shortcut_id, "Launch Failed", result="Failed", error_message=str(e))
            return {"success": False, "error": str(e)}

    def toggle_pin(self, shortcut_id):
        favs = self._load_favorites()
        state = self.states.get(shortcut_id)
        if not state:
            return False

        if shortcut_id in favs:
            favs.remove(shortcut_id)
            state.is_pinned = False
        else:
            favs.add(shortcut_id)
            state.is_pinned = True

        self._save_favorites(favs)
        self._broadcast_state_change(state)
        return state.is_pinned

    def pick_shortcut_background(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state or not self._window:
            return {"success": False, "error": "Shortcut not found."}
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                file_types=("Images (*.png;*.jpg;*.jpeg;*.webp;*.bmp)",),
            )
            if not selected:
                return {"success": True, "cancelled": True}
            source = Path(selected[0])
            if source.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
                return {"success": False, "error": "Choose a PNG, JPG, WebP, or BMP image."}
            if source.stat().st_size > 20 * 1024 * 1024:
                return {"success": False, "error": "Image must be smaller than 20 MB."}
            with Image.open(source) as image:
                image.verify()
            digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
            self.card_backgrounds_dir.mkdir(parents=True, exist_ok=True)
            destination = self.card_backgrounds_dir / f"{digest}{source.suffix.lower()}"
            if source.resolve() != destination.resolve() and not destination.exists():
                shutil.copy2(source, destination)
            relative = f"card_backgrounds/{destination.name}"
            customs = self._load_customizations()
            customs.setdefault(shortcut_id, {})["background"] = relative
            if not self._save_customizations(customs):
                return {"success": False, "error": "Could not save image selection."}
            state.custom_background = str(destination)
            return {"success": True, "custom_background": self._background_data(destination)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def clear_shortcut_background(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state:
            return {"success": False, "error": "Shortcut not found."}
        customs = self._load_customizations()
        if shortcut_id in customs:
            customs[shortcut_id].pop("background", None)
            if not any(customs[shortcut_id].values()):
                del customs[shortcut_id]
            if not self._save_customizations(customs):
                return {"success": False, "error": "Could not save image selection."}
        state.custom_background = None
        return {"success": True}

    def open_folder(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state:
            return False

        folder = None
        if state.target_exe_path:
            p = Path(state.target_exe_path)
            if p.exists():
                folder = str(p if p.is_dir() else p.parent)

        if not folder and state.working_directory and Path(state.working_directory).exists():
            folder = state.working_directory

        if folder and os.path.exists(folder):
            os.startfile(folder)
            self._log_event(shortcut_id, "Open Folder", result="Opened")
            return True
        return False

    def get_related_ini(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state:
            return {"found": False, "filename": "", "content": "Shortcut not found"}

        ini_path = None
        if state.working_directory and Path(state.working_directory).exists():
            wd = Path(state.working_directory)
            target = wd / "rk7man.ini"
            if target.exists():
                ini_path = str(target)
            else:
                inis = list(wd.glob("*.ini"))
                if inis:
                    ini_path = str(inis[0])

        if not ini_path and state.target_exe_path and Path(state.target_exe_path).exists():
            p = Path(state.target_exe_path).parent
            target = p / "rk7man.ini"
            if target.exists():
                ini_path = str(target)
            else:
                inis = list(p.glob("*.ini"))
                if inis:
                    ini_path = str(inis[0])

        if ini_path and os.path.exists(ini_path):
            try:
                with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                return {"found": True, "path": ini_path, "filename": Path(ini_path).name, "content": content}
            except Exception as e:
                return {"found": False, "path": ini_path, "filename": "ERROR", "content": f"Could not read file: {e}"}

        return {"found": False, "path": "", "filename": "NO INI FOUND", "content": "No configuration file (.ini) detected for this shortcut."}

    def get_ini_file(self, file_path):
        path = Path(file_path).resolve() if file_path else None
        owner = next((sid for sid in self.states if path and any(path == Path(item["path"]).resolve() for item in self.list_ini_files(sid))), None)
        if not owner:
            return {"found": False, "content": "INI file is outside the configured environments"}
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            self._log_event(owner, "Open INI", result=path.name)
            return {"found": True, "path": str(path), "filename": path.name, "content": content}
        except OSError as exc:
            return {"found": False, "content": str(exc)}

    def save_ini(self, file_path, content):
        path = Path(file_path).resolve() if file_path else None
        if not path or not path.is_file() or path.suffix.lower() != ".ini":
            return {"success": False, "error": "INI file does not exist"}
        if not any(path == Path(item["path"]).resolve() for sid in self.states for item in self.list_ini_files(sid)):
            return {"success": False, "error": "INI file is outside the configured environments"}
        if not os.access(path, os.W_OK):
            return {"success": False, "error": "INI file is read-only"}
        try:
            backup = path.with_name(path.name + "." + time.strftime("%Y%m%d-%H%M%S") + "." + uuid.uuid4().hex[:8] + ".bak")
            shutil.copy2(path, backup)
            temp = path.with_name(path.name + ".rk7tmp")
            try:
                temp.write_text(content, encoding="utf-8")
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
            return {"success": True, "backup": str(backup)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_ini_files(self, shortcut_id):
        state = self.states.get(shortcut_id)
        if not state:
            return []
        folders = [Path(state.working_directory)] if state.working_directory else []
        if state.target_exe_path:
            folders.append(Path(state.target_exe_path).parent)
        found = {}
        for folder in folders:
            if folder.is_dir():
                for path in folder.glob("*.ini"):
                    found[str(path.resolve()).lower()] = {"name": path.name, "path": str(path)}
        priority = {"rk7.ini": 0, "cash.ini": 1, "netk.ini": 2}
        return sorted(found.values(), key=lambda item: (priority.get(item["name"].lower(), 3), item["name"].lower()))

    def save_settings(self, new_settings):
        path = Path(str(new_settings.get("shortcut_root", "")).strip()).expanduser()
        if not path.is_dir():
            return {"success": False, "error": "Shortcut folder does not exist."}
        previous = self.settings.copy()
        self.settings["shortcut_root"] = str(path.resolve())
        if not self._save_settings():
            self.settings = previous
            return {"success": False, "error": "Could not save settings.json."}
        self.shortcut_dir = path
        shortcuts = self.refresh_shortcuts()
        return {"success": True, "settings": self.settings, "shortcuts": shortcuts, "stats": self.get_stats()}

    def browse_shortcut_folder(self):
        if not self._window:
            return {"success": False, "error": "Window is not ready."}
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, directory=str(self.shortcut_dir)
            )
            return {"success": True, "path": selected[0] if selected else None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_vault_settings(self):
        return {"path": str(self.script_repo.vault_dir)}

    def browse_vault_folder(self):
        if not self._window:
            return {"success": False, "error": "Window is not ready."}
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.FOLDER, directory=str(self.script_repo.vault_dir)
            )
            return {"success": True, "path": selected[0] if selected else None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def save_vault_folder(self, folder):
        path = Path(str(folder).strip()).expanduser()
        if not path.is_dir():
            return {"success": False, "error": "Script folder does not exist."}
        previous = self.settings.copy()
        self.settings["script_vault_dir"] = str(path.resolve())
        if not self._save_settings():
            self.settings = previous
            return {"success": False, "error": "Could not save settings.json."}
        if not self.script_repo.set_vault_dir(str(path)):
            self.settings = previous
            self._save_settings()
            return {"success": False, "error": "Could not open script folder."}
        return {"success": True, "path": self.settings["script_vault_dir"], "count": len(self.script_repo.snippets)}

    def import_script_files(self, collision="rename"):
        if not self._window:
            return {"success": False, "error": "Window is not ready."}
        try:
            selected = self._window.create_file_dialog(
                webview.FileDialog.OPEN,
                directory=str(self.script_repo.vault_dir),
                allow_multiple=True,
                file_types=("Scripts (*.sql;*.txt;*.text;*.xml;*.py;*.bat;*.cmd;*.ps1;*.pas;*.dps;*.sh;*.json;*.ini;*.cfg;*.md)",)
            )
            if not selected:
                return {"success": True, "cancelled": True, "count": 0}
            count = self.script_repo.import_files(selected, collision)
            for imported in self.script_repo.last_imported_paths:
                self._vault_files().log(imported, "Imported")
            existing = self.script_repo.last_import_existing
            errors = self.script_repo.last_import_errors
            return {"success": count > 0 or existing > 0, "count": count,
                    "already_present": existing,
                    "error": "; ".join(errors) if errors else "No files were imported." if count == 0 and existing == 0 else ""}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def import_script_blobs(self, files, collision="rename"):
        if collision not in ("skip", "rename", "replace") or not isinstance(files, list) or len(files) > 100:
            return {"success": False, "error": "Invalid import request"}
        imported, skipped, errors = 0, 0, []
        root = self.script_repo.vault_dir.resolve()
        for item in files:
            try:
                name = item["name"]
                if not isinstance(name, str) or not name or name != Path(name).name or any(c in name for c in '<>:"/\\|?*'):
                    raise ValueError("Invalid file name")
                if Path(name).suffix.lower() not in self.script_repo.SUPPORTED_EXTENSIONS:
                    raise ValueError("Unsupported file type")
                payload = base64.b64decode(item["base64"], validate=True)
                if len(payload) > 5 * 1024 * 1024:
                    raise ValueError("File exceeds 5 MB")
                destination = root / name
                if destination.exists():
                    if collision == "skip":
                        skipped += 1
                        continue
                    if collision == "rename":
                        index = 2
                        while destination.exists():
                            destination = root / f"{Path(name).stem} ({index}){Path(name).suffix}"
                            index += 1
                    else:
                        backup_dir = root / ".rk7_vault_backups"
                        backup_dir.mkdir(exist_ok=True)
                        shutil.copy2(destination, backup_dir / f"{int(time.time() * 1000000)}__{name}")
                if destination.exists():
                    temp = destination.with_name(".rk7-import-" + uuid.uuid4().hex)
                    temp.write_bytes(payload)
                    try:
                        os.replace(temp, destination)
                    finally:
                        temp.unlink(missing_ok=True)
                else:
                    with destination.open("xb") as stream:
                        stream.write(payload)
                key = self.script_repo._meta_key(destination)
                if key not in self.script_repo._meta_cache and destination.name not in self.script_repo._meta_cache:
                    detected = ScriptSnippet(destination).file_type
                    self.script_repo._meta_cache[key] = {"title": destination.stem, "description": "",
                        "tags": ["#SQL" if detected == "SQL" else "#SCRIPT"], "is_favorite": False}
                self._vault_files().log(destination, "Imported")
                imported += 1
            except Exception as exc:
                errors.append(f"{item.get('name', 'file') if isinstance(item, dict) else 'file'}: {exc}")
        if imported:
            self.script_repo._save_meta()
            self.script_repo.scan()
        return {"success": not errors, "count": imported, "skipped": skipped, "errors": errors}

    def get_scripts(self):
        """Fetch scripts from script repository."""
        snippets = self.script_repo.scan()
        items = []
        for s in snippets:
            items.append({
                "id": str(s.file_path),
                "name": s.title or s.name,
                "filename": s.filename,
                "file_type": s.file_type,
                "description": s.description,
                "tags": s.tags,
                "size_bytes": s.size_bytes,
                "line_count": s.line_count,
                "preview_snippet": s.preview_snippet,
                "is_favorite": s.is_favorite,
                "modified": s.get_modified_str(),
                "modified_timestamp": s.modified_time,
                "created_timestamp": s.created_time,
                "last_viewed": s.last_viewed,
                "language": s.meta.get("language") or s.file_type,
            })
        return items

    def _vault_files(self):
        return VaultFiles(self.script_repo.vault_dir)

    def _vault_snippet(self, file_path):
        target = self._vault_files().checked(file_path)
        return next((s for s in self.script_repo.snippets if s.file_path.resolve() == target), None)

    def get_script(self, file_path):
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet:
                return {"success": False, "error": "Script not found"}
            data = self._vault_files().read(file_path)
            self.script_repo.record_viewed(snippet)
            self._vault_files().log(file_path, "Opened")
            data.update({"success": True, "draft": self._vault_files().get_draft(file_path), "last_viewed": snippet.last_viewed})
            return data
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def search_script_content(self, query):
        needle = str(query).strip().casefold()
        if len(needle) < 2:
            return []
        matches = []
        for snippet in self.script_repo.snippets:
            try:
                if snippet.size_bytes <= 2 * 1024 * 1024 and needle in self._vault_files().read(snippet.file_path)["content"].casefold():
                    matches.append(str(snippet.file_path))
            except (OSError, UnicodeError, ValueError):
                continue
        return matches

    def save_script_draft(self, file_path, content, base_hash):
        try:
            if not self._vault_snippet(file_path):
                raise ValueError("Script not found")
            self._vault_files().save_draft(file_path, content, base_hash)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_script_history(self, file_path):
        try:
            return self._vault_files().history(file_path)
        except Exception:
            return []

    def discard_script_draft(self, file_path):
        try:
            self._vault_files().discard_draft(file_path)
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def update_script_metadata(self, file_path, description, tags, language):
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet:
                raise ValueError("Script not found")
            if not isinstance(description, str) or len(description) > 4000 or not isinstance(tags, list) or len(tags) > 30 or any(not isinstance(t, str) or len(t) > 80 for t in tags):
                raise ValueError("Invalid metadata")
            allowed = {"SQL", "Delphi", "Batch", "PowerShell", "Python", "XML", "JSON", "Text", "Shell", "Markdown", "Config"}
            if language not in allowed:
                raise ValueError("Unsupported language")
            record = self.script_repo._editable_meta(snippet)
            record.update(description=description, tags=tags, language=language)
            if not self.script_repo._save_meta():
                raise OSError("Could not save metadata")
            snippet.description, snippet.tags, snippet.file_type = description, tags, language
            snippet.meta = record
            return {"success": True}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def script_file_action(self, file_path, action, name=None):
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet:
                raise ValueError("Script not found")
            files = self._vault_files()
            old_key = self.script_repo._meta_key(snippet.file_path)
            if action == "folder":
                os.startfile(str(snippet.file_path.parent))
                return {"success": True}
            if action == "duplicate":
                new_path = files.duplicate(file_path, name)
                self.script_repo._meta_cache[self.script_repo._meta_key(Path(new_path))] = dict(self.script_repo._meta_for(snippet.file_path))
                files.log(new_path, "Duplicated")
            elif action == "rename":
                new_path = files.rename(file_path, name)
                self.script_repo._meta_cache[self.script_repo._meta_key(Path(new_path))] = dict(self.script_repo._meta_for(snippet.file_path))
                self.script_repo._meta_cache.pop(old_key, None)
                files.log(new_path, "Renamed", previous_path=file_path)
            elif action == "delete":
                files.delete_to_trash(file_path)
                self.script_repo._meta_cache.pop(old_key, None)
                new_path = None
            else:
                raise ValueError("Unsupported action")
            self.script_repo._save_meta()
            self.script_repo.scan()
            return {"success": True, "id": new_path}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def save_script_as(self, file_path, name, content, encoding, newline="\n"):
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet:
                raise ValueError("Script not found")
            destination = self._vault_files().destination(file_path, name)
            if encoding not in ("utf-8-sig", "utf-8", "utf-16", "cp1252") or newline not in ("\n", "\r\n", "\r"):
                raise ValueError("Unsupported text format")
            payload = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline).encode(encoding)
            with destination.open("xb") as stream:
                stream.write(payload)
            self.script_repo._meta_cache[self.script_repo._meta_key(destination)] = dict(self.script_repo._meta_for(snippet.file_path))
            self.script_repo._save_meta()
            self.script_repo.scan()
            self._vault_files().log(destination, "Saved As")
            return {"success": True, "id": str(destination)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def export_script(self, file_path):
        if not self._window:
            return {"success": False, "error": "Window is not ready"}
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet:
                raise ValueError("Script not found")
            selected = self._window.create_file_dialog(webview.FileDialog.SAVE, save_filename=snippet.filename)
            if not selected:
                return {"success": True, "cancelled": True}
            destination = Path(selected[0])
            if destination.exists():
                return {"success": False, "error": "Export destination already exists"}
            shutil.copy2(snippet.file_path, destination)
            return {"success": True, "path": str(destination)}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def get_script_folders(self):
        return self.script_repo.list_folders()

    def create_script(self, name, file_type, folder, content):
        try:
            snippet = self.script_repo.create_script(name, file_type, folder, content)
            return {"success": True, "id": str(snippet.file_path), "filename": snippet.filename,
                    "file_type": snippet.file_type}
        except FileExistsError:
            return {"success": False, "error": "A script with this name already exists in that folder."}
        except (ValueError, OSError) as exc:
            return {"success": False, "error": str(exc)}

    def toggle_script_favorite(self, file_path):
        for s in self.script_repo.snippets:
            if str(s.file_path) == file_path:
                fav = self.script_repo.toggle_favorite(s)
                return {"success": True, "is_favorite": fav}
        return {"success": False, "error": "Script not found"}

    def save_script(self, file_path, content, expected_hash=None, encoding=None, newline="\n"):
        try:
            snippet = self._vault_snippet(file_path)
            if not snippet or not expected_hash or not encoding:
                return {"success": False, "error": "Open the script before saving"}
            data = self._vault_files().write(file_path, content, expected_hash, encoding, newline)
            self._vault_files().discard_draft(file_path)
            snippet.refresh()
            snippet.file_type = snippet.meta.get("language") or snippet.file_type
            self._vault_files().log(file_path, "Saved")
            return {"success": True, "hash": data["hash"], "encoding": data["encoding"], "modified": data["modified"], "file_type": snippet.file_type}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def _broadcast_state_change(self, state):
        if self._window:
            js = f"window.onShortcutStateChanged && window.onShortcutStateChanged({json.dumps(state.id)}, {str(state.is_running).lower()}, {str(state.is_pinned).lower()}, {json.dumps(self._shortcut_status(state))});"
            try:
                self._window.evaluate_js(js)
            except Exception:
                pass

    def _process_tracker_loop(self):
        """Background thread scanning active shortcuts."""
        while self._tracking_active:
            try:
                time.sleep(2.0)
                active_states = [s for s in self.states.values() if s.is_running]
                if not active_states:
                    continue

                for state in active_states:
                    is_alive = False
                    if state.process_id and psutil.pid_exists(state.process_id):
                        try:
                            p = psutil.Process(state.process_id)
                            if p.status() != psutil.STATUS_ZOMBIE and (not state.target_exe_path or os.path.normcase(os.path.abspath(p.exe())) == os.path.normcase(os.path.abspath(state.target_exe_path))):
                                is_alive = True
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            pass

                    shared_target = state.target_exe_path and sum(
                        1 for other in self.states.values()
                        if other.target_exe_path and os.path.normcase(os.path.abspath(other.target_exe_path)) == os.path.normcase(os.path.abspath(state.target_exe_path))
                    ) > 1
                    if not is_alive and state.target_exe_path and not shared_target:
                        for proc in psutil.process_iter(['pid', 'name', 'exe']):
                            try:
                                if proc.info['exe'] and os.path.normcase(os.path.abspath(proc.info['exe'])) == os.path.normcase(os.path.abspath(state.target_exe_path)):
                                    state.process_id = proc.info['pid']
                                    is_alive = True
                                    self._log_event(state.id, "Process Detected", process_id=state.process_id, result="Executable path matched")
                                    break
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                continue

                    if not is_alive:
                        if state.is_running:
                            self._log_event(state.id, "Process Exited", process_id=state.process_id, result="PID no longer active")
                        state.is_running = False
                        state.process_id = None
                        state.tracking_mode = "stopped"
                        self._broadcast_state_change(state)

            except Exception as e:
                time.sleep(3.0)

    # --- Auto Update APIs ---
    def check_app_update(self):
        """Check GitHub Releases for app updates."""
        try:
            from rk7_pro.core.auto_update_service import AutoUpdateService
            updater = AutoUpdateService()
            return updater.check_update()
        except Exception as e:
            return {"has_update": False, "error": str(e)}

    def start_app_update(self, download_url, file_name=None):
        """Download and install update."""
        try:
            from rk7_pro.core.auto_update_service import AutoUpdateService
            updater = AutoUpdateService()
            def _on_progress(pct, downloaded, total, error=None):
                if self._window:
                    try:
                        err_str = (error or "").replace("'", "\\'")
                        self._window.evaluate_js(f"if (window.onAppUpdateProgress) window.onAppUpdateProgress({pct}, {downloaded}, {total}, '{err_str}');")
                    except Exception:
                        pass
            return updater.start_update(download_url, file_name, progress_callback=_on_progress)
        except Exception as e:
            return {"success": False, "error": str(e)}
