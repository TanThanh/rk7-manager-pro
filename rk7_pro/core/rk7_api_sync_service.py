"""Service for connecting directly to RK7 XML API to test connections and sync master data."""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import ssl
import time
import urllib.request
import base64
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import sys

logger = logging.getLogger("rk7_pro.api_master_sync")


def _get_base_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


class Rk7ApiSyncService:
    @classmethod
    def get_config_file(cls) -> Path:
        base = _get_base_data_dir()
        file = base / "api_connections.json"
        if file.is_file():
            return file
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass_file = Path(sys._MEIPASS) / "api_connections.json"
            if meipass_file.is_file():
                return meipass_file
        source_file = Path(__file__).resolve().parents[2] / "api_connections.json"
        if source_file.is_file():
            return source_file
        return file

    @classmethod
    def get_master_refs_dir(cls) -> Path:
        base = _get_base_data_dir()
        d = base / "master_refs"
        if d.is_dir() and any(d.iterdir()):
            return d
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass_d = Path(sys._MEIPASS) / "master_refs"
            if meipass_d.is_dir():
                return meipass_d
        source_d = Path(__file__).resolve().parents[2] / "master_refs"
        if source_d.is_dir():
            return source_d
        return d

    @classmethod
    def load_connections(cls) -> List[Dict[str, Any]]:
        """Load list of RK7 API connection profiles."""
        config_file = cls.get_config_file()
        if not config_file.is_file():
            default_profiles = [
                {
                    "id": "api_qsr_prod",
                    "name": "QSR Việt Nam",
                    "type": "api",
                    "package_id": "qsr_masterdata",
                    "url": "https://61.28.234.200:1188/rk7api/v0/xmlinterface.xml",
                    "user": "httpapi",
                    "password": "1",
                    "last_synced": None,
                    "stats": {}
                }
            ]
            cls.save_connections(default_profiles)
            return default_profiles
        try:
            conns = json.loads(config_file.read_text(encoding="utf-8"))
            # Ensure each connection has type="api"
            for c in conns:
                c.setdefault("type", "api")
            return conns
        except Exception as e:
            logger.error("Failed to load api_connections.json: %s", e)
            return []

    @classmethod
    def save_connections(cls, connections: List[Dict[str, Any]]) -> bool:
        """Save API connection profiles to json."""
        try:
            config_file = cls.get_config_file()
            config_file.write_text(
                json.dumps(connections, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            return True
        except Exception as e:
            logger.error("Failed to save api_connections.json: %s", e)
            return False

    @staticmethod
    def _create_ssl_context():
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        try:
            ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        except Exception:
            pass
        try:
            ctx.minimum_version = ssl.TLSVersion.TLSv1
        except Exception:
            pass
        return ctx

    @classmethod
    def normalize_url(cls, raw: str) -> str:
        s = (raw or "").strip()
        if not s:
            return ""
        if s.startswith("http://") or s.startswith("https://"):
            if "/rk7api/v0/xmlinterface.xml" not in s:
                s = s.rstrip("/") + "/rk7api/v0/xmlinterface.xml"
            return s
        s = re.sub(r"^https?://", "", s, flags=re.I).lstrip("/")
        parts = s.split("/")
        host_port = parts[0].strip()
        if ":" not in host_port:
            host_port = f"{host_port}:1188"
        return f"https://{host_port}/rk7api/v0/xmlinterface.xml"

    @classmethod
    def test_connection(cls, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Test read-only XML connection to RK7 API."""
        url = cls.normalize_url(profile.get("url", ""))
        user = profile.get("user", "").strip() or "httpapi"
        password = profile.get("password", "").strip() or "1"

        if not url:
            return {"success": False, "error": "Vui lòng nhập đường dẫn API URL (ví dụ: https://.../rk7api/v0/xmlinterface.xml)"}

        try:
            ctx = cls._create_ssl_context()
            auth_str = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
            xml_query = '<?xml version="1.0" encoding="utf-8"?><RK7Query><RK7CMD CMD="GetRefList"/></RK7Query>'

            req = urllib.request.Request(url, data=xml_query.encode("utf-8"))
            req.add_header("Authorization", f"Basic {auth_str}")
            req.add_header("Content-Type", "application/xml; charset=utf-8")

            t0 = time.time()
            with urllib.request.urlopen(req, context=ctx, timeout=12) as resp:
                content = resp.read()
                elapsed = round((time.time() - t0) * 1000)

            tree = ET.fromstring(content)
            server_version = tree.attrib.get("ServerVersion", "N/A")
            net_name = tree.attrib.get("NetName", "")
            status = tree.attrib.get("Status", "")

            if status != "Ok":
                err_text = tree.attrib.get("ErrorText", status)
                return {"success": False, "error": f"Lỗi từ máy chủ RK7: {err_text}"}

            ref_count = len(tree.findall(".//RK7Reference"))

            return {
                "success": True,
                "message": f"Kết nối thành công tới RK7 Server ({net_name}) trong {elapsed}ms!",
                "server_version": server_version,
                "net_name": net_name,
                "ref_tables_count": ref_count
            }
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return {"success": False, "error": "Lỗi 401 Unauthorized: Sai tên đăng nhập/mật khẩu hoặc tài khoản chưa có quyền 'HTTP API'."}
            return {"success": False, "error": f"Lỗi HTTP {e.code}: {e.reason}"}
        except Exception as e:
            return {"success": False, "error": f"Lỗi kết nối API: {str(e)}"}

    @classmethod
    def sync_master_data(cls, profile_id_or_dict: Any, progress_callback: Optional[Any] = None) -> Dict[str, Any]:
        """Fetch all master tables from RK7 XML API and save to master_refs with live progress callback."""
        if isinstance(profile_id_or_dict, str):
            connections = cls.load_connections()
            profile = next((p for p in connections if p.get("id") == profile_id_or_dict), None)
            if not profile:
                return {"success": False, "error": f"Không tìm thấy cấu hình kết nối #{profile_id_or_dict}"}
        else:
            profile = profile_id_or_dict
            connections = cls.load_connections()

        url = cls.normalize_url(profile.get("url", ""))
        user = profile.get("user", "").strip() or "httpapi"
        password = profile.get("password", "").strip() or "1"
        package_id = re.sub(r"[^a-zA-Z0-9_]", "_", profile.get("package_id") or profile.get("id") or "master").lower().strip("_")

        def report(step: int, total: int, table: str, status: str, message: str, count: Optional[int] = None):
            if progress_callback:
                try:
                    progress_callback(step, total, table, status, message, count)
                except Exception as ex:
                    logger.debug("Error calling progress_callback: %s", ex)

        ctx = cls._create_ssl_context()
        auth_str = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")

        def fetch_ref_xml(ref_name: str, extra_attrs: str = "") -> ET.Element:
            xml_payload = f'<?xml version="1.0" encoding="utf-8"?><RK7Query><RK7CMD CMD="GetRefData" RefName="{ref_name}"{extra_attrs}/></RK7Query>'
            req = urllib.request.Request(url, data=xml_payload.encode("utf-8"))
            req.add_header("Authorization", f"Basic {auth_str}")
            req.add_header("Content-Type", "application/xml; charset=utf-8")
            with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
                return ET.fromstring(resp.read())

        start_time = time.time()
        TOTAL_STEPS = 12

        try:
            # 1. RESTAURANTS
            report(1, TOTAL_STEPS, "RESTAURANTS", "running", "Đang tải danh sách nhà hàng...")
            restaurants = {}
            tree = fetch_ref_xml("RESTAURANTS", ' OnlyActive="0"')
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                status = it.attrib.get("Status", "")
                if sifr and sifr != "0" and status != "rsDeleted":
                    restaurants[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", ""),
                        "guid": it.attrib.get("GUIDString", ""),
                        "concept": it.attrib.get("Concept", "")
                    }
            report(1, TOTAL_STEPS, "RESTAURANTS", "done", f"Tải thành công {len(restaurants)} cơ sở", len(restaurants))

            # 2. PRICETYPES
            report(2, TOTAL_STEPS, "PRICETYPES", "running", "Đang tải các bậc đơn giá...")
            price_scales = {}
            tree = fetch_ref_xml("PRICETYPES")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    price_scales[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", ""),
                        "guid": it.attrib.get("GUIDString", "")
                    }
            report(2, TOTAL_STEPS, "PRICETYPES", "done", f"Tải thành công {len(price_scales)} bậc giá", len(price_scales))

            # 3. EMPLOYEES
            report(3, TOTAL_STEPS, "EMPLOYEES", "running", "Đang tải danh sách nhân viên...")
            employees = {}
            tree = fetch_ref_xml("EMPLOYEES", ' OnlyActive="0"')
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                status = it.attrib.get("Status", "")
                if sifr and sifr != "0" and status != "rsDeleted":
                    employees[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(3, TOTAL_STEPS, "EMPLOYEES", "done", f"Tải thành công {len(employees)} nhân viên", len(employees))

            # 4. CURRENCIES & CURRENCYTYPES
            report(4, TOTAL_STEPS, "CURRENCIES", "running", "Đang tải hình thức thanh toán & loại tiền...")
            currencies = {}
            tree = fetch_ref_xml("CURRENCIES")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    currencies[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }

            currency_types = {}
            tree = fetch_ref_xml("CURRENCYTYPES")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    currency_types[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(4, TOTAL_STEPS, "CURRENCIES", "done", f"Tải thành công {len(currencies)} loại tiền tệ", len(currencies))

            # 5. DISCOUNTS
            report(5, TOTAL_STEPS, "DISCOUNTS", "running", "Đang tải danh mục chiết khấu & khuyến mãi...")
            discounts = {}
            tree = fetch_ref_xml("DISCOUNTS")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    discounts[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(5, TOTAL_STEPS, "DISCOUNTS", "done", f"Tải thành công {len(discounts)} loại khuyến mãi", len(discounts))

            # 6. TRADEGROUPS
            report(6, TOTAL_STEPS, "TRADEGROUPS", "running", "Đang tải nhóm bán hàng...")
            trade_groups = {}
            tree = fetch_ref_xml("TRADEGROUPS")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    trade_groups[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", ""),
                        "price_type": it.attrib.get("PriceType") or None
                    }
            report(6, TOTAL_STEPS, "TRADEGROUPS", "done", f"Tải thành công {len(trade_groups)} nhóm bán hàng", len(trade_groups))

            # 7. UNCHANGEABLEORDERTYPES
            report(7, TOTAL_STEPS, "ORDERTYPES", "running", "Đang tải danh mục loại đơn hàng...")
            order_types = {}
            tree = fetch_ref_xml("UNCHANGEABLEORDERTYPES")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    order_types[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(7, TOTAL_STEPS, "ORDERTYPES", "done", f"Tải thành công {len(order_types)} loại đơn hàng", len(order_types))

            # 8. CATEGLIST
            report(8, TOTAL_STEPS, "CATEGLIST", "running", "Đang tải cây nhóm thực đơn...")
            categories = {}
            tree = fetch_ref_xml("CATEGLIST")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    categories[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", ""),
                        "parent": it.attrib.get("Parent") or it.attrib.get("MainParentIdent") or None
                    }
            report(8, TOTAL_STEPS, "CATEGLIST", "done", f"Tải thành công {len(categories)} nhóm thực đơn", len(categories))

            # 9. TABLES
            report(9, TOTAL_STEPS, "TABLES", "running", "Đang tải danh mục bàn...")
            tables = {}
            tree = fetch_ref_xml("TABLES")
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    tables[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(9, TOTAL_STEPS, "TABLES", "done", f"Tải thành công {len(tables)} bàn", len(tables))

            # 10. MODIFIERS
            report(10, TOTAL_STEPS, "MODIFIERS", "running", "Đang tải danh mục món phụ & topping (dung lượng lớn)...")
            modifiers = {}
            tree = fetch_ref_xml("MODIFIERS", ' OnlyActive="1"')
            for it in tree.findall(".//Item"):
                sifr = it.attrib.get("Ident")
                if sifr and sifr != "0":
                    modifiers[sifr] = {
                        "code": int(it.attrib.get("Code", 0)) if it.attrib.get("Code", "").isdigit() else it.attrib.get("Code", ""),
                        "name": it.attrib.get("Name", "")
                    }
            report(10, TOTAL_STEPS, "MODIFIERS", "done", f"Tải thành công {len(modifiers)} mục món phụ", len(modifiers))

            # 11. GENERATEDPROPTYPES & GENERATEDPROPDATAS
            report(11, TOTAL_STEPS, "PROPERTIES", "running", "Đang bóc tách mã SAP, MONTV, NOTINVOICE...")
            prop_names = {}
            try:
                tree = fetch_ref_xml("GENERATEDPROPTYPES")
                for it in tree.findall(".//Item"):
                    p_id = it.attrib.get("Ident")
                    p_name = it.attrib.get("Name") or it.attrib.get("RKPropName") or ""
                    if p_id and p_name:
                        prop_names[p_id] = p_name.strip()
            except Exception as e_p:
                logger.debug("Failed fetching GENERATEDPROPTYPES: %s", e_p)

            props_by_dish = {}
            try:
                tree = fetch_ref_xml("GENERATEDPROPDATAS", ' IgnoreFilter="true"')
                for it in tree.findall(".//Item"):
                    obj_refno = it.attrib.get("ObjectRefNo")
                    if obj_refno in ("10", None, ""):
                        obj_ident = it.attrib.get("ObjectIdent")
                        rktype = it.attrib.get("RKTypeIdent")
                        prop_val = it.attrib.get("PropertyVal", "").strip()
                        if obj_ident and rktype and prop_val:
                            if obj_ident not in props_by_dish:
                                props_by_dish[obj_ident] = {}
                            props_by_dish[obj_ident][rktype] = prop_val
            except Exception as e_d:
                logger.debug("Failed fetching GENERATEDPROPDATAS: %s", e_d)
            report(11, TOTAL_STEPS, "PROPERTIES", "done", f"Bóc tách thuộc tính thành công ({len(props_by_dish)} món)", len(props_by_dish))

            # Helper fetches for detailed dish mapping: PRICES, MODISCHEMES, TAXDISHTYPES
            prices_by_dish = {}
            try:
                p_tree = fetch_ref_xml("PRICES")
                for pit in p_tree.findall(".//Item"):
                    d_id = pit.attrib.get("ObjectID") or pit.attrib.get("ItemIdent")
                    # In RK7 XML, price scale is linked via PriceType
                    ps_id = pit.attrib.get("PriceType") or pit.attrib.get("PriceScale") or pit.attrib.get("PriceScaleIdent")
                    val = pit.attrib.get("Value") or pit.attrib.get("Price")
                    if d_id and val is not None:
                        d_id_str = str(d_id)
                        if d_id_str not in prices_by_dish:
                            prices_by_dish[d_id_str] = []
                        ps_info = price_scales.get(ps_id, {})
                        scale_name = ps_info.get("name") if ps_info else (f"Bậc {ps_id}" if ps_id else "Mặc định")
                        scale_code = ps_info.get("code", "") if ps_info else ""
                        try:
                            # RK7 money is stored in cents (1/100 VND)
                            val_num = round(float(val) / 100.0, 2)
                        except Exception:
                            val_num = val
                        prices_by_dish[d_id_str].append({
                            "scale_id": ps_id,
                            "scale_code": scale_code,
                            "scale_name": scale_name,
                            "price": val_num
                        })
            except Exception as e_pr:
                logger.debug("Failed fetching PRICES: %s", e_pr)

            modi_schemes = {}
            try:
                ms_tree = fetch_ref_xml("MODISCHEMES")
                for ms_it in ms_tree.findall(".//Item"):
                    ms_id = ms_it.attrib.get("Ident")
                    if ms_id:
                        modi_schemes[ms_id] = ms_it.attrib.get("Name", "")
            except Exception as e_ms:
                logger.debug("Failed fetching MODISCHEMES: %s", e_ms)

            tax_dish_types = {}
            try:
                td_tree = fetch_ref_xml("TAXDISHTYPES")
                for td_it in td_tree.findall(".//Item"):
                    td_id = td_it.attrib.get("Ident")
                    if td_id:
                        tax_dish_types[td_id] = td_it.attrib.get("Name", "")
            except Exception as e_td:
                logger.debug("Failed fetching TAXDISHTYPES: %s", e_td)

            # 12. MENUITEMS
            report(12, TOTAL_STEPS, "MENUITEMS", "running", "Đang tải và ánh xạ toàn bộ thực đơn món ăn...")
            menu_items = {}
            tree = fetch_ref_xml("MENUITEMS")
            for it in tree.findall(".//Item"):
                sifr_str = it.attrib.get("Ident")
                if not sifr_str or sifr_str == "0":
                    continue
                raw_u = it.attrib.get("PortionName", "").strip()
                unit_norm = raw_u
                if raw_u == "Phần":
                    unit_norm = "POR"
                elif raw_u == "Lon":
                    unit_norm = "BOT"

                dish_props = props_by_dish.get(sifr_str, {})
                sapcode_val = dish_props.get("10", "")
                if not sapcode_val:
                    for r_key, r_val in dish_props.items():
                        if "SAP" in prop_names.get(r_key, "").upper():
                            sapcode_val = r_val
                            break
                if not sapcode_val:
                    sapcode_val = it.attrib.get("ExtCode", "")

                montv_name = dish_props.get("1000025", "")
                not_invoice_flag = (dish_props.get("1000046") == "1")
                code_raw = it.attrib.get("Code", "")
                code_val = int(code_raw) if code_raw.isdigit() else code_raw

                m_scheme_id = it.attrib.get("ModiScheme", "")
                m_scheme_name = modi_schemes.get(m_scheme_id, "")
                t_group_id = it.attrib.get("TradeGroup", "")
                t_group_name = trade_groups.get(t_group_id, {}).get("name", "") if t_group_id in trade_groups else ""
                t_dish_id = it.attrib.get("TaxDishType", "") or it.attrib.get("TaxRate", "")
                t_dish_name = tax_dish_types.get(t_dish_id, "")

                status_raw = it.attrib.get("Status", "3")
                status_label = "Active" if status_raw == "3" else ("Suspended" if status_raw in ("1", "2") else "Deleted" if status_raw == "0" else f"Status {status_raw}")

                menu_items[sifr_str] = {
                    "code": code_val,
                    "name": it.attrib.get("Name", ""),
                    "altname": it.attrib.get("AltName", ""),
                    "status": status_label,
                    "status_code": status_raw,
                    "montv": montv_name,
                    "not_invoice": not_invoice_flag,
                    "categ": it.attrib.get("Parent") or None,
                    "unit": unit_norm,
                    "portion_weight": it.attrib.get("PortionWeight", ""),
                    "sapcode": sapcode_val,
                    "props": dish_props,
                    "external_code": it.attrib.get("ExtCode", ""),
                    "barcodes": it.attrib.get("Barcodes", ""),
                    "tax_group_id": t_dish_id,
                    "tax_group_name": t_dish_name,
                    "modi_scheme_id": m_scheme_id,
                    "modi_scheme_name": m_scheme_name,
                    "trade_group_id": t_group_id,
                    "trade_group_name": t_group_name,
                    "start_date": it.attrib.get("StartDate", ""),
                    "end_date": it.attrib.get("EndDate", ""),
                    "start_time": it.attrib.get("StartTime", ""),
                    "end_time": it.attrib.get("EndTime", ""),
                    "sale_limits": it.attrib.get("SaleLimits", ""),
                    "prices": prices_by_dish.get(sifr_str, [])
                }
            report(12, TOTAL_STEPS, "MENUITEMS", "done", f"Ánh xạ thành công {len(menu_items)} món ăn", len(menu_items))

            # Compile into standard master JSON
            master_data = {
                "package_id": package_id,
                "display_name": profile.get("name") or package_id,
                "exported_at": datetime.now().isoformat(),
                "source": f"RK7 XML API ({url})",
                "total_restaurants": len(restaurants),
                "total_menu_items": len(menu_items),
                "total_price_scales": len(price_scales),
                "total_employees": len(employees),
                "restaurants": restaurants,
                "price_scales": price_scales,
                "employees": employees,
                "currencies": currencies,
                "currency_types": currency_types,
                "discounts": discounts,
                "trade_groups": trade_groups,
                "menu_items": menu_items,
                "order_types": order_types,
                "modifiers": modifiers,
                "tables": tables,
                "categories": categories,
                "property_types": prop_names,
                "tax_dish_types": tax_dish_types,
                "modifier_schemes": modi_schemes
            }

            # Write master json file
            master_refs_dir = cls.get_master_refs_dir()
            master_refs_dir.mkdir(parents=True, exist_ok=True)
            target_json = master_refs_dir / f"{package_id}.json"
            target_json.write_text(json.dumps(master_data, indent=2, ensure_ascii=False), encoding="utf-8")

            # Update index_map.json
            from .ref_master_service import RefMasterService
            ref_svc = RefMasterService(storage_dir=master_refs_dir)
            index_data = ref_svc._load_index()
            index_data.setdefault("packages", {})[package_id] = {
                "package_id": package_id,
                "display_name": profile.get("name") or package_id,
                "file": f"{package_id}.json",
                "source_file": f"API: {url}",
                "restaurants_count": len(restaurants),
                "menu_items_count": len(menu_items),
                "price_scales_count": len(price_scales),
                "size_kb": round(target_json.stat().st_size / 1024, 1)
            }
            index_data.setdefault("restaurants", {})
            for r_id, r_info in restaurants.items():
                index_data["restaurants"][r_id] = {
                    "package_id": package_id,
                    "name": r_info.get("name")
                }
            ref_svc._index_map = index_data
            ref_svc._save_index()

            # Update last synced time in profile
            duration = round(time.time() - start_time, 1)
            stats = {
                "restaurants_count": len(restaurants),
                "menu_items_count": len(menu_items),
                "employees_count": len(employees),
                "tables_count": len(tables),
                "duration_sec": duration
            }

            # Find and update profile in connections list
            if isinstance(profile_id_or_dict, str):
                for p in connections:
                    if p.get("id") == profile_id_or_dict:
                        p["last_synced"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        p["stats"] = stats
                        break
                cls.save_connections(connections)

            report(12, TOTAL_STEPS, "FINISHED", "done", f"Hoàn tất đồng bộ trong {duration}s! (File: {round(target_json.stat().st_size / 1024, 1)} KB)")

            return {
                "success": True,
                "message": f"Đồng bộ thành công Master Data '{package_id}' từ RK7 API trong {duration}s!",
                "stats": stats,
                "package_id": package_id,
                "file_size_kb": round(target_json.stat().st_size / 1024, 1)
            }

        except Exception as e:
            logger.error("API Sync failed: %s", e)
            report(0, TOTAL_STEPS, "ERROR", "error", f"Lỗi đồng bộ: {str(e)}")
            return {"success": False, "error": f"Lỗi đồng bộ RK7 API: {str(e)}"}
