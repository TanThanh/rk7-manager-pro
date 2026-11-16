import datetime
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from rk7_pro.core.ref_master_service import RefMasterService

# Base time for Delphi / RK7 timestamps (30/12/1899)
BASE_DELPHI_TIME = datetime.datetime(1899, 12, 30)

def fix_vn_text(text):
    """Restore Vietnamese text encoded as CP1258 but read as CP1252 / latin1.
    If the text is already valid UTF-8 Vietnamese (or ASCII), preserve it without corrupting.
    """
    if not text:
        return ""
    if text.isascii():
        return text
    try:
        # If it was originally CP1258 bytes misdecoded as CP1252, every character fits in CP1252 (0x00-0xFF).
        # Genuine UTF-8 Vietnamese characters (like 'ộ', 'ệ', 'đ', 'ả', 'ư', 'ơ') will fail encoding to CP1252
        # (UnicodeEncodeError) -> which correctly indicates it is ALREADY valid UTF-8!
        raw_bytes = text.encode("cp1252")
        fixed = raw_bytes.decode("cp1258")
        return unicodedata.normalize("NFC", fixed)
    except Exception:
        # Already valid UTF-8 or standard text, do not replace with '?'
        return unicodedata.normalize("NFC", text)

def parse_rk_datetime(val):
    if not val:
        return None
    try:
        t = int(val)
        return BASE_DELPHI_TIME + datetime.timedelta(days=t / (86400 * 1000))
    except Exception:
        return None

def format_rk_time(val):
    dt = parse_rk_datetime(val)
    return dt.strftime("%H:%M") if dt else ""

def format_rk_full_datetime(val):
    dt = parse_rk_datetime(val)
    return dt.strftime("%d/%m/%Y %H:%M:%S") if dt else ""

def resolve_check_print_number(check, all_checks=None, all_orders=None):
    """Resolve PRINTNUMBER for a check. If RK7 omitted PRINTNUMBER due to printer timeout,
    deduce it by ordering checks in the shift or gap sequence.
    """
    p_num = check.get("PRINTNUMBER")
    if p_num is not None and str(p_num).strip():
        return str(p_num).strip()

    all_checks = all_checks or []
    all_orders = all_orders or []

    existing_pns = {
        int(c.get("PRINTNUMBER"))
        for c in all_checks
        if c.get("PRINTNUMBER") and str(c.get("PRINTNUMBER")).isdigit()
    }

    # Sort closed checks by BILLDATETIME (or STARTDATETIME)
    sorted_checks = sorted(
        [c for c in all_checks if c.get("STATE") == "6"],
        key=lambda x: int(x.get("BILLDATETIME") or x.get("STARTDATETIME") or 0)
    )

    target_idx = next(
        (i for i, c in enumerate(sorted_checks)
         if c.get("UNI") == check.get("UNI") and c.get("VISIT") == check.get("VISIT")),
        None
    )

    if target_idx is not None:
        prev_pn = next(
            (int(sorted_checks[i].get("PRINTNUMBER"))
             for i in range(target_idx - 1, -1, -1)
             if sorted_checks[i].get("PRINTNUMBER") and str(sorted_checks[i].get("PRINTNUMBER")).isdigit()),
            None
        )
        next_pn = next(
            (int(sorted_checks[i].get("PRINTNUMBER"))
             for i in range(target_idx + 1, len(sorted_checks))
             if sorted_checks[i].get("PRINTNUMBER") and str(sorted_checks[i].get("PRINTNUMBER")).isdigit()),
            None
        )

        if prev_pn is not None and next_pn is not None and next_pn - prev_pn == 2:
            return str(prev_pn + 1)
        elif prev_pn is not None and (prev_pn + 1) not in existing_pns:
            return str(prev_pn + 1)
        elif next_pn is not None and (next_pn - 1) > 0 and (next_pn - 1) not in existing_pns:
            return str(next_pn - 1)

    # Fallback to ORDERS.SEQNUMBER
    v_id = check.get("VISIT")
    order = next((o for o in all_orders if o.get("VISIT") == v_id), {})
    seq = order.get("SEQNUMBER")
    if seq and str(seq).isdigit() and int(seq) not in existing_pns:
        return str(seq)

    return "1"


class UdbCheckViewService:
    def __init__(self, bin_dir=None, data_dir=None):
        import sys
        self.bin_dir = None
        self.tool_exe = None

        candidate_dirs = []
        if bin_dir is not None:
            candidate_dirs.append(Path(bin_dir))
        
        # When running under PyInstaller onefile
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidate_dirs.append(Path(sys._MEIPASS) / "rk7_pro" / "bin")
            candidate_dirs.append(Path(sys._MEIPASS) / "bin")
        
        # Next to executable
        exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        candidate_dirs.append(exe_dir / "rk7_pro" / "bin")
        candidate_dirs.append(exe_dir / "bin")
        
        # Source tree location
        source_bin = Path(__file__).resolve().parent.parent / "bin"
        candidate_dirs.append(source_bin)
        candidate_dirs.append(Path(__file__).resolve().parent.parent.parent / "bin")

        for c_dir in candidate_dirs:
            target = c_dir / "udb2xml.exe"
            if target.is_file():
                self.bin_dir = c_dir.resolve()
                self.tool_exe = target.resolve()
                break

        if not self.tool_exe:
            # Fallback default
            self.bin_dir = Path(bin_dir) if bin_dir else (exe_dir / "rk7_pro" / "bin")
            self.tool_exe = self.bin_dir / "udb2xml.exe"

        exe_dir = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent.parent
        self.data_dir = Path(data_dir) if data_dir else exe_dir
        if not (self.data_dir / "master_refs").is_dir() or not any((self.data_dir / "master_refs").iterdir()):
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS") and (Path(sys._MEIPASS) / "master_refs").is_dir():
                self.data_dir = Path(sys._MEIPASS)
            else:
                source_data = Path(__file__).resolve().parent.parent.parent
                if (source_data / "master_refs").is_dir():
                    self.data_dir = source_data

        self.employees_file = self.data_dir / "employees.json"
        self._employee_map = self._load_employees()
        self.ref_service = RefMasterService(self.data_dir / "master_refs")

    def _load_employees(self):
        default_map = {
            "1006235": "Nhân viên #1006235",
            "1006236": "Phục vụ #1006236",
            "1006237": "Phục vụ #1006237",
            "1006238": "Thu ngân #1006238",
            "1006254": "Quản lý #1006254",
            "9001": "Admin / Hệ thống"
        }
        if self.employees_file.is_file():
            try:
                import json
                with open(self.employees_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    default_map.update(data)
            except Exception:
                pass
        return default_map

    def save_employee_name(self, emp_id, name):
        emp_id = str(emp_id).strip()
        name = str(name).strip()
        if not emp_id:
            return False
        self._employee_map[emp_id] = name
        try:
            import json
            with open(self.employees_file, "w", encoding="utf-8") as f:
                json.dump(self._employee_map, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get_employee_name(self, emp_id, master_data=None):
        if not emp_id:
            return "Hệ thống"
        s_id = str(emp_id)
        if master_data and "employees" in master_data:
            emp = master_data["employees"].get(s_id)
            if emp:
                if isinstance(emp, dict):
                    return emp.get("name") or emp.get("display_name") or f"NV: {s_id}"
                return str(emp)
        return self._employee_map.get(s_id, f"NV: {s_id}")

    def convert_udb_to_xml(self, udb_path, xml_path=None):
        """Convert a .udb file to .xml using local udb2xml.exe."""
        udb_file = Path(udb_path).resolve()
        if not udb_file.is_file():
            raise FileNotFoundError(f"UDB file not found: {udb_path}")
        
        if not self.tool_exe.is_file():
            raise FileNotFoundError(f"udb2xml.exe not found at {self.tool_exe}")

        if xml_path is None:
            temp_xml = tempfile.NamedTemporaryFile(suffix=".xml", delete=False)
            xml_file = Path(temp_xml.name)
            temp_xml.close()
        else:
            xml_file = Path(xml_path).resolve()

        # Run CLI in bin directory so all dependent DLLs are loaded
        # Use CREATE_NO_WINDOW on Windows to prevent black console/cmd dialog from popping up
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        result = subprocess.run(
            [str(self.tool_exe), str(udb_file), str(xml_file)],
            cwd=str(self.bin_dir),
            capture_output=True,
            text=True,
            errors="ignore",
            creationflags=creationflags
        )
        if result.returncode != 0 or not xml_file.is_file() or xml_file.stat().st_size == 0:
            raw_err = (result.stderr or result.stdout or "").strip()
            if "Page is corrupted" in raw_err:
                raise RuntimeError(f"Tệp UDB này bị lỗi cấu trúc dữ liệu hoặc chưa kết thúc ca hoàn chỉnh (Corrupted database page). Chi tiết: {raw_err}")
            raise RuntimeError(f"Không thể giải mã tệp UDB: {raw_err}")

        return xml_file

    def parse_udb_database(self, udb_path):
        """Full parse of UDB file into structured CheckView model."""
        xml_file = self.convert_udb_to_xml(udb_path)
        try:
            return self._parse_xml(xml_file, udb_path)
        finally:
            if xml_file.is_file():
                try:
                    os.unlink(xml_file)
                except Exception:
                    pass

    def _parse_xml(self, xml_path, original_udb_path):
        removed_invalid_refs = 0
        try:
            root = ET.parse(xml_path).getroot()
        except ET.ParseError as error:
            if "reference to invalid character number" not in str(error):
                raise
            # udb2xml can emit XML 1.0-invalid numeric character references
            # in auxiliary text fields. Remove only those references, leaving
            # valid entities and all other data untouched.
            source = Path(xml_path).read_bytes()

            def strip_invalid_reference(match):
                nonlocal removed_invalid_refs
                entity = match.group(0)
                value = int(entity[3:-1], 16) if entity[2:3] in (b"x", b"X") else int(entity[2:-1])
                valid = (value in (9, 10, 13) or 0x20 <= value <= 0xD7FF
                         or 0xE000 <= value <= 0xFFFD or 0x10000 <= value <= 0x10FFFF)
                if valid:
                    return entity
                removed_invalid_refs += 1
                return b""

            repaired = re.sub(rb"&#(?:[xX][0-9a-fA-F]+|[0-9]+);", strip_invalid_reference, source)
            if not removed_invalid_refs:
                raise
            root = ET.fromstring(repaired)

        tables = {}
        for t in root.findall("Table"):
            t_name = t.attrib.get("name")
            data = t.find("Data")
            recs = [r.attrib for r in data.findall("Rec")] if data is not None else []
            tables[t_name] = recs

        # 1. Header Information
        global_shifts = tables.get("GLOBALSHIFTS", [])
        last_shift = global_shifts[-1] if global_shifts else {}
        info_rec = tables.get("INFO", [{}])[0] if tables.get("INFO") else {}

        shift_num = last_shift.get("SHIFTNUM", "")
        shift_date = last_shift.get("SHIFTDATE", "")
        midserver = last_shift.get("MIDSERVER", info_rec.get("NUMBER", ""))
        restaurant = last_shift.get("IRESTAURANT", "")

        # 2. Check summary metrics
        printchecks = tables.get("PRINTCHECKS", [])
        closed_checks = [c for c in printchecks if c.get("STATE") == "6"]
        open_checks = [c for c in printchecks if c.get("STATE") == "1"]
        void_checks = [c for c in printchecks if c.get("STATE") not in ("1", "6")]

        total_prlist = sum(int(c.get("PRLISTSUM", 0) or 0) for c in closed_checks) / 100
        total_disc = sum(int(c.get("DISCOUNTSUM", 0) or 0) for c in closed_checks) / 100
        total_basic = sum(int(c.get("BASICSUM", 0) or 0) for c in closed_checks) / 100

        # Group the checks actually present in this UDB. SHIFTS.BASICSUM is a
        # station aggregate and may include checks absent from PRINTCHECKS.
        shifts_table = tables.get("SHIFTS", [])
        shift_summary_map = {}
        for s in shifts_table:
            s_num = s.get("SHIFTNUM") or ""
            shift_summary_map[s_num] = {
                "count": 0, "closed_count": 0, "open_count": 0,
                "void_count": 0, "sum": 0,
                "reported_sum": int(s.get("BASICSUM", 0) or 0) / 100,
                "has_shift_record": True,
            }
        for c in printchecks:
            s_num = c.get("ISHIFT") or ""
            group = shift_summary_map.setdefault(s_num, {
                "count": 0, "closed_count": 0, "open_count": 0,
                "void_count": 0, "sum": 0,
                "reported_sum": None, "has_shift_record": False,
            })
            group["count"] += 1
            if c.get("STATE") == "6":
                group["closed_count"] += 1
                group["sum"] += int(c.get("BASICSUM", 0) or 0) / 100
            elif c.get("STATE") == "1":
                group["open_count"] += 1
            else:
                group["void_count"] += 1

        # 3. Index data for fast lookup
        orders_by_visit = {}
        for o in tables.get("ORDERS", []):
            orders_by_visit[o.get("VISIT")] = o

        sessions_by_visit = {}
        for s in tables.get("ORDERSESSIONS", []):
            sessions_by_visit.setdefault(s.get("VISIT"), []).append(s)

        dishes_by_visit = {}
        for d in tables.get("SESSIONDISHES", []):
            dishes_by_visit.setdefault(d.get("VISIT"), []).append(d)

        sales_by_visit = {}
        for s in tables.get("SALEOBJECTS", []):
            sales_by_visit.setdefault(s.get("VISIT"), {})[s.get("DISHUNI")] = s

        modifiers_by_visit = {}
        for m in tables.get("DISHMODIFIERS", []):
            modifiers_by_visit.setdefault(m.get("VISIT"), []).append(m)

        payments_by_visit = {}
        for p in tables.get("PAYMENTS", []):
            payments_by_visit.setdefault(p.get("VISIT"), []).append(p)

        oplogs_by_visit = {}
        for l in tables.get("OPERATIONLOG", []):
            if l.get("VISIT"):
                oplogs_by_visit.setdefault(l.get("VISIT"), []).append(l)

        booking_id_by_visit = {}
        for ext in tables.get("EXTERNALIDS", []):
            v_id = ext.get("VISIT")
            if not v_id or v_id in booking_id_by_visit:
                continue
            ext_src = str(ext.get("EXTSOURCE") or "").upper()
            if str(ext.get("SIFR") or "") == "1000026" or ext_src == "{7FD7164C-8362-4BA2-8723-F45751795312}":
                val = self._norm_text(ext.get("EXTID"))
                if val:
                    booking_id_by_visit[v_id] = val

        # 4. Build checks list
        checks_list = []
        for c in printchecks:
            visit_id = c.get("VISIT")
            order = orders_by_visit.get(visit_id, {})
            state = c.get("STATE")
            state_text = "Đã đóng" if state == "6" else ("Đang mở" if state == "1" else "Đã hủy")

            close_dt = c.get("CLOSEDATETIME") or order.get("ENDSERVICE")
            basic_sum = int(c.get("BASICSUM", 0) or 0) / 100
            prlist_sum = int(c.get("PRLISTSUM", 0) or 0) / 100
            disc_sum = int(c.get("DISCOUNTSUM", 0) or 0) / 100
            tax_sum = int(c.get("TAXSUM", 0) or 0) / 100

            resolved_print_num = resolve_check_print_number(c, printchecks, tables.get("ORDERS", []))
            checks_list.append({
                "check_num": c.get("CHECKNUM", "N/A"),
                "print_num": resolved_print_num,
                "table_name": order.get("TABLENAME", "N/A"),
                "order_name": order.get("ORDERNAME", "N/A"),
                "visit_id": visit_id,
                "check_uni": c.get("UNI", ""),
                "state": state,
                "state_text": state_text,
                "close_time": format_rk_time(close_dt),
                "close_datetime": format_rk_full_datetime(close_dt),
                "open_datetime": format_rk_full_datetime(order.get("OPENTIME")),
                "guests_count": order.get("GUESTSCOUNT", c.get("GUESTCNT", "1")),
                "operator_id": c.get("IAUTHOR", order.get("IAUTHOR", "Hệ thống")),
                "station_id": c.get("IPRINTSTATION", order.get("STATIONID", "")),
                "shift_id": c.get("ISHIFT", ""),
                "prlist_sum": prlist_sum,
                "disc_sum": disc_sum,
                "basic_sum": basic_sum,
                "tax_sum": tax_sum,
                "booking_id": booking_id_by_visit.get(visit_id, ""),
            })

        # Sort checks: Closed checks first (state == '6'), then by check_num descending, then open checks
        def check_sort_key(x):
            is_closed = 1 if x["state"] == "6" else 0
            try:
                num = int(x["check_num"])
            except Exception:
                num = 0
            return (is_closed, num)

        checks_list.sort(key=check_sort_key, reverse=True)

        # Auto-resolve Master Data Package
        master_data = self.ref_service.get_master_data_for_restaurant(restaurant)
        master_info = None
        if master_data:
            master_info = {
                "has_master": True,
                "package_id": master_data.get("package_id"),
                "display_name": master_data.get("display_name") or master_data.get("package_id"),
                "restaurant_name": master_data.get("restaurants", {}).get(str(restaurant), {}).get("name", f"Nhà hàng #{restaurant}")
            }
        else:
            master_info = {
                "has_master": False,
                "package_id": None,
                "display_name": None,
                "restaurant_name": f"Nhà hàng #{restaurant}" if restaurant else "Chưa rõ"
            }

        from .invoice_xml_template_service import InvoiceXmlTemplateService
        matched_template = InvoiceXmlTemplateService.get_template_name({"header": {"restaurant": restaurant}}, master_data)
        has_xml_template = matched_template is not None

        return {
            "success": True,
            "filename": Path(original_udb_path).name,
            "header": {
                "invalid_xml_refs_removed": removed_invalid_refs,
                "shift_num": shift_num,
                "shift_date": shift_date,
                "midserver": midserver,
                "restaurant": restaurant,
                "restaurant_name": master_info["restaurant_name"],
                "master_package": master_info["package_id"],
                "master_display_name": master_info["display_name"],
                "has_xml_template": has_xml_template,
                "xml_template_name": matched_template,
                "station_id": checks_list[0]["station_id"] if checks_list else "",
                "total_checks_count": len(printchecks),
                "closed_count": len(closed_checks),
                "open_count": len(open_checks),
                "void_count": len(void_checks),
                "total_prlist": total_prlist,
                "total_disc": total_disc,
                "total_basic": total_basic,
                "shift_summary_map": shift_summary_map
            },
            "master_info": master_info,
            "checks": checks_list,
            # Cache tables for quick visit detail fetching
            "_raw_tables": tables
        }

    def get_check_view_detail(self, db_result, visit_id, check_uni=None):
        """Generate full receipt POS view and audit logs for a visit."""
        tables = db_result.get("_raw_tables", {})
        
        # Order info
        orders = [o for o in tables.get("ORDERS", []) if o.get("VISIT") == visit_id]
        order = orders[0] if orders else {}

        # Resolve Master Data
        restaurant_id = db_result.get("header", {}).get("restaurant")
        master_data = self.ref_service.get_master_data_for_restaurant(restaurant_id) if restaurant_id else None

        # Print check
        pchecks = [c for c in tables.get("PRINTCHECKS", []) if c.get("VISIT") == visit_id]
        if check_uni is not None:
            pchecks = [c for c in pchecks if c.get("UNI") == str(check_uni)]
        elif any(c.get("STATE") == "6" for c in pchecks):
            pchecks = [c for c in pchecks if c.get("STATE") == "6"]
        check = pchecks[0] if pchecks else {}

        # Payments
        payments = [p for p in tables.get("PAYMENTS", []) if p.get("VISIT") == visit_id]
        pay_methods = []
        currencies_map = (master_data or {}).get("currencies", {})
        currency_types_map = (master_data or {}).get("currency_types", {})
        for p in payments:
            line_type = p.get("PAYLINETYPE") or p.get("IHIGHLEVELTYPE")
            amount = int(p.get("BASICSUM", 0) or 0) / 100
            orig_amount = int(p.get("ORIGINALSUM", p.get("BASICSUM", 0)) or 0) / 100
            sifr = str(p.get("SIFR", "") or "")
            curr_obj = currencies_map.get(sifr) if currencies_map and sifr else None
            curr_code = curr_obj.get("code") if curr_obj else ""
            if curr_obj and curr_obj.get("name"):
                name = curr_obj["name"]
            elif line_type == "1":
                name = "Chuyển khoản / Thẻ / QR"
            elif line_type == "0":
                name = "Tiền mặt"
            else:
                name = f"Hình thức #{sifr or line_type}"

            type_obj = currency_types_map.get(str(line_type)) if currency_types_map and line_type else None
            type_name = type_obj.get("name") if type_obj else ("Tiền mặt" if line_type == "0" else ("Thẻ/Ngân hàng" if line_type == "1" else f"Nhóm #{line_type}"))

            pay_methods.append({
                "uni": p.get("UNI", ""),
                "sifr": sifr,
                "code": str(curr_code),
                "name": fix_vn_text(name),
                "type_id": str(line_type or ""),
                "type_name": fix_vn_text(type_name),
                "amount": amount,
                "original_sum": orig_amount,
                "state": p.get("STATE", "")
            })

        # Discounts
        raw_discounts = [d for d in tables.get("DISHDISCOUNTS", []) if d.get("VISIT") == visit_id]
        discounts_map = (master_data or {}).get("discounts", {})
        check_discounts = []
        for d in raw_discounts:
            d_sifr = str(d.get("SIFR", "") or "")
            d_obj = discounts_map.get(d_sifr) if discounts_map and d_sifr else None
            d_name = d_obj.get("name") if d_obj and d_obj.get("name") else f"Giảm giá #{d_sifr}"
            d_code = d_obj.get("code") if d_obj and d_obj.get("code") else ""
            raw_amt = d.get("CALCAMOUNT") or d.get("SRCAMOUNT") or 0
            d_amount = abs(int(raw_amt)) / 100
            d_base = int(d.get("DISCOUNTBASE") or 0) / 100
            d_card = str(d.get("CARDCODE", "") or "").strip()
            d_holder = fix_vn_text(d.get("HOLDER", ""))
            d_interface = str(d.get("MINTERFACE", "") or "").strip()
            check_discounts.append({
                "uni": d.get("UNI", ""),
                "sifr": d_sifr,
                "code": str(d_code),
                "name": fix_vn_text(d_name),
                "amount": d_amount,
                "base_sum": d_base,
                "card_code": d_card,
                "holder": d_holder,
                "interface": d_interface,
                "state": d.get("STATE", "")
            })

        # External IDs & CRM (Tích điểm, SkyMonitor, Haravan, Golden Spoon, Booking, v.v.)
        external_records = []
        v_str = str(visit_id)
        seen_ext_vals = set()
        for ext in tables.get("EXTERNALIDS", []):
            if str(ext.get("VISIT") or "") != v_str:
                continue
            ext_sifr = str(ext.get("SIFR") or "").strip()
            ext_src = str(ext.get("EXTSOURCE") or "").strip()
            ext_val = self._norm_text(ext.get("VALUE_UTF8") or ext.get("EXTID") or "")
            if not ext_val:
                continue

            kind = "Mã ngoài hệ thống"
            src_upper = ext_src.upper()
            if ext_sifr == "1000026" or src_upper == "{7FD7164C-8362-4BA2-8723-F45751795312}":
                kind = "Mã Booking (Đặt bàn)"
            elif ext_sifr == "1000027" or src_upper == "{12ECAFC2-8A29-4346-9F0F-AAF9BFB90202}":
                kind = "Tiền cọc Booking"
            elif ext_sifr == "1000028" or src_upper == "{70D1DBBE-8118-4A3C-9AA9-35DDCB0DC35A}":
                kind = "Ghi chú Booking"
            elif ext_sifr == "1000029" or src_upper == "{3471AF30-EE0C-425A-AD4A-B88E01719B09}":
                kind = "Số khách đặt"
            elif ext_sifr == "1000030" or src_upper == "{A2859CB8-6DC3-40C7-96AA-884B12A588B3}":
                kind = "SĐT khách đặt"
            elif ext_sifr == "10001" or src_upper == "{44727918-5294-40F8-9FF8-65270A8E2C9C}":
                kind = "Email khách đặt"
            elif ext_sifr == "10023":
                kind = "Mã Pager / Beeper / Thẻ gọi"
            elif ext_sifr == "10024":
                kind = "Mã kênh ngoài / CRM / Đối tác"
            elif "CRM" in src_upper or "MEMBER" in src_upper or "CARD" in src_upper:
                kind = "Mã CRM / Thẻ thành viên"

            seen_ext_vals.add(ext_val)
            external_records.append({
                "uni": ext.get("UNI", ""),
                "sifr": ext_sifr,
                "source": ext_src,
                "value": ext_val,
                "kind": kind,
                "order": ext.get("ORDER", "")
            })

        for cd in check_discounts:
            card = cd.get("card_code")
            if card and card not in seen_ext_vals:
                seen_ext_vals.add(card)
                external_records.append({
                    "uni": cd.get("uni", ""),
                    "sifr": cd.get("sifr", ""),
                    "source": cd.get("interface", "") or "PDS/CRM",
                    "value": card,
                    "kind": f"Thẻ tích điểm / VIP ({cd.get('holder') or 'Thành viên'})",
                    "order": ""
                })

        # Sessions and dishes
        sessions = sorted(
            [s for s in tables.get("ORDERSESSIONS", []) if s.get("VISIT") == visit_id],
            key=lambda x: int(x.get("STARTSERVICE", 0) or 0)
        )
        dishes = [d for d in tables.get("SESSIONDISHES", []) if d.get("VISIT") == visit_id]
        modifiers = [m for m in tables.get("DISHMODIFIERS", []) if m.get("VISIT") == visit_id]
        sales_map = {s.get("DISHUNI"): s for s in tables.get("SALEOBJECTS", []) if s.get("VISIT") == visit_id}
        menu_items_map = (master_data or {}).get("menu_items", {})
        modifiers_map = (master_data or {}).get("modifiers", {})

        receipt_sessions = []
        for s in sessions:
            s_uni = s.get("UNI")
            s_time = format_rk_time(s.get("STARTSERVICE"))
            scale_id = s.get("IPRICESCALE")
            scale_name = ""
            if master_data and scale_id:
                scale_obj = master_data.get("price_scales", {}).get(str(scale_id))
                if scale_obj:
                    scale_name = scale_obj.get("name", "")
            if not scale_name:
                scale_name = f"Thang giá #{scale_id}" if scale_id else "Std_Price"

            s_dishes = [d for d in dishes if d.get("SESSIONUNI") == s_uni and d.get("ISCOMBOCOMP") != "1"]
            s_payments = [p for p in payments if p.get("SESSIONUNI") == s_uni]

            items = []
            for d in s_dishes:
                uni = d.get("UNI")
                sifr = str(d.get("SIFR", "") or "")
                is_combo = d.get("ISCOMBO") == "1"
                s_obj = sales_map.get(uni)
                raw_name = ""
                if is_combo:
                    # Check order's DISHLINE1..3
                    for dl_key in ["DISHLINE1", "DISHLINE2", "DISHLINE3"]:
                        val = order.get(dl_key, "")
                        if "Combo" in val or "combo" in val.lower():
                            raw_name = val
                            break
                    if not raw_name:
                        # Fallback to menu_items from master data
                        m_dish = menu_items_map.get(sifr)
                        if m_dish and m_dish.get("name"):
                            raw_name = m_dish["name"]
                        else:
                            raw_name = f"Combo #{d.get('SIFR') or uni}"
                elif s_obj:
                    raw_name = s_obj.get("NAME", "")
                else:
                    m_dish = menu_items_map.get(sifr)
                    if m_dish and m_dish.get("name"):
                        raw_name = m_dish["name"]
                    else:
                        raw_name = f"Món #{uni}"

                dish_name = fix_vn_text(raw_name)
                
                q_val = d.get("QUANTITY")
                src_qnt = int(d.get("SRCQUANTITY") or 0) / 1000
                writeoff_qnt = int(d.get("WRITEOFFQUANTITY") or 0) / 1000
                if q_val is not None:
                    qnt = int(q_val) / 1000
                elif writeoff_qnt > 0:
                    qnt = 0
                else:
                    qnt = src_qnt if src_qnt > 0 else 1.0
                is_void = (qnt == 0 and src_qnt > 0) or (writeoff_qnt >= src_qnt and src_qnt > 0)
                total_price = int(d.get("PRLISTSUM", 0) or 0) / 100
                raw_price = d.get("PRICE") or d.get("MENUITEMPRICE")
                if raw_price is not None:
                    unit_price = int(raw_price or 0) / 100
                elif qnt > 0 and total_price > 0:
                    unit_price = total_price / qnt
                else:
                    unit_price = total_price

                pay_sum = int(d.get("PAYSUM", 0) or 0) / 100
                net_price = int(d.get("SUMWITHDISCOUNTS", d.get("PRLISTSUM", 0)) or 0) / 100
                is_combo = d.get("ISCOMBO") == "1"

                combo_comps = []
                if is_combo:
                    comps = [c for c in dishes if c.get("COMBODISHUNI") == uni]
                    for comp in comps:
                        c_uni = comp.get("UNI")
                        c_sifr = str(comp.get("SIFR", "") or "")
                        c_dish = menu_items_map.get(c_sifr) if menu_items_map else None
                        c_s = sales_map.get(c_uni)
                        if c_s and c_s.get("NAME"):
                            c_raw_name = c_s.get("NAME")
                        elif c_dish and c_dish.get("name"):
                            c_raw_name = c_dish["name"]
                        else:
                            c_raw_name = f"Thành phần #{c_uni}"
                        c_name = fix_vn_text(c_raw_name)
                        c_qnt = int(comp.get("QUANTITY", 1000) or 1000) / 1000
                        c_pay = int(comp.get("PAYSUM", 0) or 0) / 100
                        c_net_price = int(comp.get("SUMWITHDISCOUNTS", comp.get("PRLISTSUM", 0)) or 0) / 100
                        c_raw_price = comp.get("PRICE") or comp.get("MENUITEMPRICE")
                        c_total_price = int(comp.get("PRLISTSUM", 0) or 0) / 100
                        if c_raw_price is not None:
                            c_unit_price = int(c_raw_price or 0) / 100
                        elif c_qnt > 0 and c_total_price > 0:
                            c_unit_price = c_total_price / c_qnt
                        else:
                            c_unit_price = c_total_price

                        comp_mods = []
                        for m in modifiers:
                            if m.get("DISHUNI") == c_uni and m.get("COMBODISHUNI") != c_uni:
                                m_sifr = str(m.get("SIFR", "") or "")
                                m_open = m.get("OPENNAME", "")
                                if m_open:
                                    m_raw = m_open
                                else:
                                    m_obj = modifiers_map.get(m_sifr)
                                    m_raw = m_obj.get("name") if m_obj else f"Modifier #{m_sifr}"
                                comp_mods.append(fix_vn_text(m_raw))

                        c_dish_code = (c_dish.get("code") if c_dish else "") or (c_s.get("CODE") if c_s else "") or ""
                        c_tax = comp.get("TAXRATE") or (c_dish.get("tax_rate") if c_dish else "") or ""

                        combo_comps.append({
                            "uni": c_uni,
                            "dish_uni": c_uni,
                            "sifr": c_sifr,
                            "code": str(c_dish_code),
                            "price_scale_id": scale_id or "",
                            "price_scale_name": scale_name,
                            "session_uni": s_uni,
                            "name": c_name,
                            "quantity": int(c_qnt),
                            "unit_price": c_unit_price,
                            "price": c_total_price,
                            "total_price": c_total_price,
                            "net_price": c_net_price,
                            "pay_sum": c_pay,
                            "tax_rate": c_tax,
                            "modifiers": comp_mods
                        })
                    if raw_name.startswith("Combo #") and combo_comps:
                        dish_name = "Combo: " + " + ".join(comp["name"] for comp in combo_comps)

                # Direct dish modifiers
                dish_mods = []
                for m in modifiers:
                    if m.get("DISHUNI") == uni and not is_combo:
                        m_sifr = str(m.get("SIFR", "") or "")
                        m_open = m.get("OPENNAME", "")
                        if m_open:
                            m_raw = m_open
                        else:
                            m_obj = modifiers_map.get(m_sifr)
                            m_raw = m_obj.get("name") if m_obj else f"Modifier #{m_sifr}"
                        dish_mods.append(fix_vn_text(m_raw))

                m_dish_obj = menu_items_map.get(sifr) if menu_items_map else None
                dish_code = (m_dish_obj.get("code") if m_dish_obj else "") or (s_obj.get("CODE") if s_obj else "") or ""
                tax_rate_val = d.get("TAXRATE") or (m_dish_obj.get("tax_rate") if m_dish_obj else "") or ""

                items.append({
                    "uni": uni,
                    "dish_uni": uni,
                    "sifr": sifr,
                    "code": str(dish_code),
                    "price_scale_id": scale_id or "",
                    "price_scale_name": scale_name,
                    "session_uni": s_uni,
                    "name": dish_name,
                    "quantity": int(qnt),
                    "unit_price": unit_price,
                    "price": total_price,
                    "total_price": total_price,
                    "net_price": net_price,
                    "pay_sum": pay_sum,
                    "is_combo": is_combo,
                    "is_charge": bool(d.get("CHARGEUNI")),
                    "is_void": is_void,
                    "void_qnt": int(writeoff_qnt or src_qnt),
                    "tax_rate": tax_rate_val,
                    "combo_components": combo_comps,
                    "modifiers": dish_mods
                })

            pay_items = []
            for p in s_payments:
                line_type = p.get("PAYLINETYPE")
                amount = int(p.get("BASICSUM", 0) or 0) / 100
                sifr = str(p.get("SIFR", "") or "")
                curr_obj = currencies_map.get(sifr) if currencies_map and sifr else None
                if curr_obj and curr_obj.get("name"):
                    name = curr_obj["name"]
                elif line_type == "1":
                    name = "Chuyển khoản / Thẻ / QR"
                elif line_type == "0":
                    name = "Tiền mặt"
                else:
                    name = f"Hình thức #{line_type}"
                pay_items.append({
                    "name": name,
                    "amount": amount,
                    "code": p.get("SIFR")
                })

            if items or pay_items:
                op_id = s.get("IAUTHOR") or s.get("ICREATOR")
                # Check employee name from master data
                op_name = ""
                if master_data and op_id:
                    emp_obj = master_data.get("employees", {}).get(str(op_id))
                    if emp_obj:
                        op_name = emp_obj.get("name", "")
                if not op_name:
                    op_name = self.get_employee_name(op_id)

                receipt_sessions.append({
                    "session_uni": s_uni,
                    "time": s_time,
                    "operator_id": op_id,
                    "operator": op_name,
                    "price_scale_id": scale_id,
                    "price_scale_name": scale_name,
                    "items": items,
                    "payments": pay_items
                })

        # Build Table Name Mapping
        table_names_map = {}
        for o in tables.get("ORDERS", []):
            t_id = str(o.get("TABLEID") or "")
            t_name = str(o.get("TABLENAME") or "")
            if t_id and t_name and t_id not in table_names_map:
                table_names_map[t_id] = t_name
        if master_data and "tables" in master_data:
            for t_id, t_info in master_data["tables"].items():
                if isinstance(t_info, dict) and t_info.get("name"):
                    table_names_map.setdefault(str(t_id), t_info["name"])
        for t in tables.get("TABLES", []):
            t_id = str(t.get("SIFR") or "")
            t_name = str(t.get("NAME") or "")
            if t_id and t_name:
                table_names_map.setdefault(t_id, t_name)

        # 3. Audit operation logs
        op_logs = [l for l in tables.get("OPERATIONLOG", []) if l.get("VISIT") == visit_id]
        audit_trail = []
        for l in op_logs:
            op_code = str(l.get("OPERATION") or "")
            param_val = l.get("PARAMETER")
            op_id = l.get("OPERATOR")
            mgr_id = l.get("MANAGER")

            trail_item = {
                "time": format_rk_full_datetime(l.get("DATETIME")),
                "operator_id": op_id,
                "operator": self.get_employee_name(op_id, master_data),
                "manager_id": mgr_id,
                "manager": self.get_employee_name(mgr_id, master_data) if (mgr_id and mgr_id != op_id) else None,
                "operation_code": op_code,
                "parameter": param_val,
                "station": l.get("STATION"),
                "sum_after": int(l.get("ORDERSUMAFTER", 0) or 0) / 100 if l.get("ORDERSUMAFTER") else None
            }

            # Check if this is a table transfer operation (Op 249: Change order table, Op 491: Transfer table)
            if op_code in ["249", "491"]:
                source_table_id = str(param_val) if param_val else None
                source_table_name = table_names_map.get(source_table_id, f"Bàn #{source_table_id}") if source_table_id else "N/A"
                dest_table_name = order.get("TABLENAME", "N/A")
                trail_item["table_transfer"] = {
                    "is_transfer": True,
                    "from_table_id": source_table_id,
                    "from_table_name": source_table_name,
                    "to_table_id": order.get("TABLEID"),
                    "to_table_name": dest_table_name,
                    "operator_name": trail_item["operator"],
                    "manager_name": trail_item["manager"],
                    "description": f"Chuyển từ bàn {source_table_name} sang bàn {dest_table_name}"
                }

            audit_trail.append(trail_item)

        # Check overall order table transfer status (In & Out via ORDERSESSIONS)
        transfer_summary = []
        for s in tables.get("ORDERSESSIONS", []):
            if str(s.get("VISIT") or "") == str(visit_id) and str(s.get("ISESSIONTYPE") or "") == "2":
                src_v = str(s.get("EXTRAVISIT") or s.get("COMMONVISIT") or "")
                src_order = next((o for o in tables.get("ORDERS", []) if str(o.get("VISIT") or "") == src_v), None)
                src_tname = src_order.get("TABLENAME") if src_order else table_names_map.get(str(s.get("EXTRAORDERIDENT") or ""))
                transfer_summary.append({
                    "direction": "in",
                    "from_table": src_tname or f"Lượt #{src_v}",
                    "to_table": order.get("TABLENAME", "N/A"),
                    "from_visit": src_v,
                    "time": format_rk_full_datetime(s.get("STARTSERVICE")),
                    "operator": self.get_employee_name(s.get("ICREATOR") or s.get("IAUTHOR"), master_data),
                    "operator_id": s.get("ICREATOR") or s.get("IAUTHOR")
                })
                break

        for s in tables.get("ORDERSESSIONS", []):
            if str(s.get("EXTRAVISIT") or "") == str(visit_id) and str(s.get("VISIT") or "") != str(visit_id):
                dest_v = str(s.get("VISIT") or "")
                dest_order = next((o for o in tables.get("ORDERS", []) if str(o.get("VISIT") or "") == dest_v), None)
                dest_tname = dest_order.get("TABLENAME") if dest_order else f"Lượt #{dest_v}"
                transfer_summary.append({
                    "direction": "out",
                    "from_table": order.get("TABLENAME", "N/A"),
                    "to_table": dest_tname,
                    "to_visit": dest_v,
                    "time": format_rk_full_datetime(s.get("STARTSERVICE")),
                    "operator": self.get_employee_name(s.get("ICREATOR") or s.get("IAUTHOR"), master_data),
                    "operator_id": s.get("ICREATOR") or s.get("IAUTHOR")
                })
                break

        main_op_id = check.get("IAUTHOR") or order.get("IAUTHOR", "")
        charge_sum = int(check.get("CHARGEPRICELISTSUM", 0) or 0) / 100
        resolved_print_num = resolve_check_print_number(check, tables.get("PRINTCHECKS", []), tables.get("ORDERS", []))
        booking_info = self._extract_booking_info(tables, visit_id)
        return {
            "success": True,
            "visit_id": visit_id,
            "check_uni": check.get("UNI", ""),
            "check_num": check.get("CHECKNUM", "N/A"),
            "print_num": resolved_print_num,
            "shift_id": check.get("ISHIFT", ""),
            "table_name": order.get("TABLENAME", "N/A"),
            "order_name": order.get("ORDERNAME", "N/A"),
            "booking_id": booking_info.get("booking_id", ""),
            "booking": booking_info,
            "close_time": format_rk_time(check.get("CLOSEDATETIME") or order.get("ENDSERVICE")),
            "close_datetime": format_rk_full_datetime(check.get("CLOSEDATETIME") or order.get("ENDSERVICE")),
            "open_datetime": format_rk_full_datetime(order.get("OPENTIME")),
            "guests_count": order.get("GUESTSCOUNT", check.get("GUESTCNT", "1")),
            "state_text": "Đã đóng" if check.get("STATE") == "6" else "Đang mở",
            "station_id": check.get("IPRINTSTATION", order.get("STATIONID", "")),
            "operator_id": main_op_id,
            "operator_name": self.get_employee_name(main_op_id, master_data),
            "transfer_summary": transfer_summary,
            "price_scale_name": (receipt_sessions[0].get("price_scale_name") if receipt_sessions else ""),
            "financial": {
                "prlist_sum": int(check.get("PRLISTSUM", 0) or 0) / 100,
                "charge_sum": charge_sum,
                "disc_sum": int(check.get("DISCOUNTSUM", 0) or 0) / 100,
                "basic_sum": int(check.get("BASICSUM", 0) or 0) / 100,
                "tax_sum": int(check.get("TAXSUM", 0) or 0) / 100,
            },
            "discounts": check_discounts,
            "payments": pay_methods,
            "external_ids": external_records,
            "receipt_sessions": receipt_sessions,
            "audit_trail": audit_trail
        }

    def build_check_xml(self, db_result, visit_id, check_uni):
        """Export one selected check using the sh01350 reconstructed XML format."""
        visit_id, check_uni = str(visit_id), str(check_uni)
        raw_check = next((row for row in db_result.get("_raw_tables", {}).get("PRINTCHECKS", [])
                          if row.get("VISIT") == visit_id and row.get("UNI") == check_uni), None)
        if raw_check is None:
            raise ValueError("Không tìm thấy check trong file UDB hiện tại.")
        detail = self.get_check_view_detail(db_result, visit_id, check_uni)
        root = ET.Element("CheckExport", {
            "sourceFile": db_result.get("filename", ""),
            "origin": "UDB-reconstructed",
            "checkNumber": str(raw_check.get("CHECKNUM", "")),
            "visit": visit_id,
            "checkUni": check_uni,
        })
        raw = ET.SubElement(root, "RawPrintCheck")
        for key, value in raw_check.items():
            ET.SubElement(raw, "Field", {"name": key}).text = str(value)

        child_tags = {
            "receipt_sessions": "session", "items": "item",
            "combo_components": "component", "modifiers": "modifier",
            "payments": "payment", "audit_trail": "event",
        }

        def append(parent, key, value):
            node = ET.SubElement(parent, key)
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    append(node, child_key, child_value)
            elif isinstance(value, list):
                for entry in value:
                    append(node, child_tags.get(key, "entry"), entry)
            else:
                node.text = "" if value is None else str(value)

        receipt = ET.SubElement(root, "ReconstructedReceipt")
        for key, value in detail.items():
            if key not in ("success", "audit_trail"):
                append(receipt, key, value)
        ET.indent(root, space="  ")
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _parse_int(val, default=0):
        try:
            if val is None or str(val).strip() == "":
                return default
            return int(float(str(val).strip()))
        except Exception:
            return default

    @staticmethod
    def _norm_text(val, fallback=""):
        text = fix_vn_text(val) if val else ""
        return unicodedata.normalize("NFC", text).strip() or fallback

    @staticmethod
    def _fmt_k80_amount(val):
        num = int(round(val or 0))
        return "0" if num == 0 else f"{num:,}"

    @staticmethod
    def _k80_row(left, right="", width=42):
        left_s = str(left or "")
        right_s = str(right or "")
        if not right_s:
            return left_s[:width]
        max_left = max(1, width - len(right_s) - 1)
        if len(left_s) > max_left:
            left_s = left_s[:max_left]
        spaces = max(1, width - len(left_s) - len(right_s))
        return f"{left_s}{' ' * spaces}{right_s}"

    @staticmethod
    def _k80_center(text, width=42):
        s = str(text or "")
        if len(s) >= width:
            return s[:width]
        pad = (width - len(s)) // 2
        return (" " * pad) + s

    def _resolve_employee_display(self, emp_id, master_data):
        if not emp_id:
            return ""
        emp_key = str(emp_id).strip()
        if master_data:
            emp_obj = (master_data.get("employees") or {}).get(emp_key)
            if emp_obj and emp_obj.get("name"):
                return self._norm_text(emp_obj["name"])
        return self._norm_text(self.get_employee_name(emp_key))

    def _extract_booking_info(self, tables, visit_id):
        """Extract CVL booking metadata (Booking ID, deposit, note, guests, phone, email) from EXTERNALIDS."""
        info = {
            "booking_id": "",
            "deposit": 0.0,
            "note": "",
            "guests": "",
            "phone": "",
            "email": "",
        }
        if not visit_id:
            return info

        v_str = str(visit_id)
        for ext in tables.get("EXTERNALIDS", []):
            if str(ext.get("VISIT") or "") != v_str:
                continue
            sifr = str(ext.get("SIFR") or "").strip()
            src = str(ext.get("EXTSOURCE") or "").upper()
            val = self._norm_text(ext.get("EXTID"))
            if not val:
                continue

            if sifr == "1000026" or src == "{7FD7164C-8362-4BA2-8723-F45751795312}":
                if not info["booking_id"]:
                    info["booking_id"] = val
            elif sifr == "1000027" or src == "{12ECAFC2-8A29-4346-9F0F-AAF9BFB90202}":
                try:
                    info["deposit"] = float(val)
                except Exception:
                    pass
            elif sifr == "1000028" or src == "{70D1DBBE-8118-4A3C-9AA9-35DDCB0DC35A}":
                if not info["note"]:
                    info["note"] = val
            elif sifr == "1000029" or src == "{3471AF30-EE0C-425A-AD4A-B88E01719B09}":
                if not info["guests"]:
                    info["guests"] = val
            elif sifr == "1000030" or src == "{A2859CB8-6DC3-40C7-96AA-884B12A588B3}":
                if not info["phone"]:
                    info["phone"] = val
            elif sifr == "10001" or src == "{44727918-5294-40F8-9FF8-65270A8E2C9C}":
                if not info["email"]:
                    info["email"] = val

        return info

    def get_shift_handover_report(self, db_result, shift_num=None):
        """Build cashier shift handover report (CVL FO.201 layout) from parsed UDB tables."""
        if not db_result:
            raise ValueError("Chưa tải dữ liệu UDB.")

        tables = db_result.get("_raw_tables", {})
        header = db_result.get("header", {})
        restaurant_id = header.get("restaurant")
        master_data = self.ref_service.get_master_data_for_restaurant(restaurant_id) if restaurant_id else None

        printchecks = tables.get("PRINTCHECKS", [])
        payments = tables.get("PAYMENTS", [])
        paybindings = tables.get("PAYBINDINGS", [])
        currlines = tables.get("CURRLINES", [])
        discparts = tables.get("DISCPARTS", [])
        orders = tables.get("ORDERS", [])
        shifts_rows = tables.get("SHIFTS", [])
        global_shifts = tables.get("GLOBALSHIFTS", [])

        gshift_by_num = {str(g.get("SHIFTNUM")): g for g in global_shifts if g.get("SHIFTNUM")}
        orders_by_visit = {o.get("VISIT"): o for o in orders if o.get("VISIT")}
        currline_by_key = {
            (c.get("VISIT"), c.get("UNI")): c
            for c in currlines if c.get("VISIT") and c.get("UNI")
        }
        check_by_key = {
            (c.get("VISIT"), c.get("UNI")): c
            for c in printchecks if c.get("VISIT") and c.get("UNI")
        }
        paybinding_by_key = {
            (pb.get("VISIT"), pb.get("UNI")): pb
            for pb in paybindings if pb.get("VISIT") and pb.get("UNI")
        }

        closed_checks_all = [c for c in printchecks if c.get("STATE") == "6"]

        # Build shift selector list from SHIFTS and closed checks
        shift_meta = {}
        for s in shifts_rows:
            s_num = str(s.get("SHIFTNUM") or "").strip()
            if not s_num:
                continue
            icomm = str(s.get("ICOMMONSHIFT") or "").strip()
            g_row = gshift_by_num.get(icomm, {})
            shift_meta[s_num] = {
                "shift_num": s_num,
                "common_shift": icomm,
                "shift_date": g_row.get("SHIFTDATE") or header.get("shift_date") or "",
                "station_id": str(s.get("ISTATION") or s.get("IPRINTSTATION") or ""),
                "manager_id": str(s.get("IMANAGER") or ""),
                "closed": s.get("CLOSED") == "1",
                "is_last_shift": s.get("ISLASTSHIFT") == "1",
                "reported_sum": self._parse_int(s.get("BASICSUM"), 0) / 100 if s.get("BASICSUM") is not None else None,
                "closed_count": 0,
                "closed_sum": 0.0,
            }

        for c in closed_checks_all:
            s_num = str(c.get("ISHIFT") or "").strip()
            if not s_num:
                continue
            icomm = str(c.get("ICOMMONSHIFT") or "").strip()
            g_row = gshift_by_num.get(icomm, {})
            entry = shift_meta.setdefault(s_num, {
                "shift_num": s_num,
                "common_shift": icomm,
                "shift_date": g_row.get("SHIFTDATE") or header.get("shift_date") or "",
                "station_id": str(c.get("IPRINTSTATION") or c.get("ICLOSESTATION") or ""),
                "manager_id": str(c.get("IAUTHOR") or ""),
                "closed": False,
                "is_last_shift": False,
                "reported_sum": None,
                "closed_count": 0,
                "closed_sum": 0.0,
            })
            entry["closed_count"] += 1
            entry["closed_sum"] += self._parse_int(c.get("BASICSUM"), 0) / 100
            if not entry["common_shift"] and icomm:
                entry["common_shift"] = icomm
                entry["shift_date"] = g_row.get("SHIFTDATE") or entry["shift_date"]

        def _shift_sort_key(item):
            s_id = item["shift_num"]
            return (0, int(s_id)) if s_id.isdigit() else (1, s_id)

        available_shifts = sorted(shift_meta.values(), key=_shift_sort_key)

        # Determine target shift filter
        req_shift = str(shift_num).strip() if shift_num is not None else ""
        if not req_shift or req_shift.upper() == "AUTO":
            shifts_with_closed = [s for s in available_shifts if s["closed_count"] > 0]
            if len(shifts_with_closed) == 1:
                selected_shift = shifts_with_closed[0]["shift_num"]
            elif len(shifts_with_closed) > 1:
                selected_shift = shifts_with_closed[-1]["shift_num"]
            elif available_shifts:
                selected_shift = available_shifts[-1]["shift_num"]
            else:
                selected_shift = "ALL"
        elif req_shift.upper() == "ALL":
            selected_shift = "ALL"
        else:
            selected_shift = req_shift

        selected_meta = shift_meta.get(selected_shift) if selected_shift != "ALL" else None
        target_common_shift = (
            selected_meta["common_shift"]
            if selected_meta and selected_meta.get("common_shift")
            else str(header.get("shift_num") or "").strip()
        )

        def _check_in_scope(check_row):
            if selected_shift == "ALL":
                return True
            return str(check_row.get("ISHIFT") or "").strip() == selected_shift

        closed_checks = [c for c in closed_checks_all if _check_in_scope(c)]

        # Unpaid checks matching .mak: STATE not Closed/Deleted, FLAGS != 2, within current common shift
        unpaid_checks = []
        stale_open_count = 0
        for c in printchecks:
            state = c.get("STATE")
            if state in ("6", "7"):
                continue
            if c.get("DELETED") == "1" or c.get("IGNOREINREP") == "1" or c.get("FLAGS") == "2":
                continue
            if selected_shift != "ALL" and target_common_shift:
                if str(c.get("ICOMMONSHIFT") or "").strip() != target_common_shift:
                    stale_open_count += 1
                    continue
            has_activity = (
                self._parse_int(c.get("BINDEDSUM"), 0) > 0
                or c.get("GUESTCNT") is not None
                or bool(c.get("CHECKNUM"))
            )
            if has_activity:
                unpaid_checks.append(c)

        # 1. Revenue summary from PAYBINDINGS (STATE == 6) joined via CURRLINES -> PRINTCHECKS
        scoped_paybindings = []
        for pb in paybindings:
            if pb.get("STATE") != "6":
                continue
            if selected_shift != "ALL":
                cl = currline_by_key.get((pb.get("VISIT"), pb.get("CURRUNI")))
                pc = check_by_key.get((pb.get("VISIT"), cl.get("CHECKUNI"))) if cl else None
                if not pc or not _check_in_scope(pc):
                    continue
            scoped_paybindings.append(pb)

        if scoped_paybindings:
            gross_revenue = sum(self._parse_int(pb.get("PAYSUM"), 0) for pb in scoped_paybindings) / 100
            total_discount = sum(self._parse_int(pb.get("DISTRDISCOUNTS"), 0) for pb in scoped_paybindings) / 100
            vat_amount = sum(self._parse_int(pb.get("TAXESADDED"), 0) for pb in scoped_paybindings) / 100
            pre_tax_amount = sum(
                self._parse_int(pb.get("PRICESUM"), 0) + self._parse_int(pb.get("DISTRDISCOUNTS"), 0)
                for pb in scoped_paybindings
            ) / 100
            revenue_source = "PAYBINDINGS"
        else:
            gross_revenue = sum(self._parse_int(c.get("BASICSUM"), 0) for c in closed_checks) / 100
            total_discount = -sum(self._parse_int(c.get("DISCOUNTSUM"), 0) for c in closed_checks) / 100
            vat_amount = sum(self._parse_int(c.get("TAXSUMADDED") or c.get("TAXSUM"), 0) for c in closed_checks) / 100
            pre_tax_amount = gross_revenue - vat_amount
            revenue_source = "PRINTCHECKS"

        # 2. Currency breakdown from PAYMENTS (STATE == 6)
        currencies_map = (master_data or {}).get("currencies", {})
        currency_types_map = (master_data or {}).get("currency_types", {})
        scoped_payments = [
            p for p in payments
            if p.get("STATE") == "6"
            and (selected_shift == "ALL" or str(p.get("ISHIFT") or "").strip() == selected_shift)
        ]

        type_groups = {}
        total_paid = 0.0
        for p in scoped_payments:
            basic_val = self._parse_int(p.get("BASICSUM"), 0) / 100
            orig_val = self._parse_int(p.get("ORIGINALSUM"), 0) / 100
            total_paid += basic_val

            ht_id = str(p.get("IHIGHLEVELTYPE") or "").strip()
            sifr = str(p.get("SIFR") or "").strip()

            ht_obj = currency_types_map.get(ht_id) if ht_id else None
            if ht_obj and ht_obj.get("name"):
                ht_name = self._norm_text(ht_obj["name"])
            elif p.get("PAYLINETYPE") == "0":
                ht_name = "Tiền mặt"
            elif ht_id:
                ht_name = f"Loại tiền #{ht_id}"
            else:
                ht_name = "Khác"

            curr_obj = currencies_map.get(sifr) if sifr else None
            if curr_obj and curr_obj.get("name"):
                curr_name = self._norm_text(curr_obj["name"])
            elif sifr:
                curr_name = f"Tiền tệ #{sifr}"
            else:
                curr_name = ht_name

            grp = type_groups.setdefault(ht_id or ht_name, {
                "type_id": ht_id,
                "type_name": ht_name,
                "total": 0.0,
                "items": {}
            })
            grp["total"] += basic_val

            item = grp["items"].setdefault(sifr or curr_name, {
                "sifr": sifr,
                "name": curr_name,
                "basic_sum": 0.0,
                "original_sum": 0.0,
                "tx_count": 0,
            })
            item["basic_sum"] += basic_val
            item["original_sum"] += orig_val
            if basic_val >= 0:
                item["tx_count"] += 1

        currency_groups = []
        for grp in type_groups.values():
            items_list = sorted(grp["items"].values(), key=lambda x: x["basic_sum"], reverse=True)
            currency_groups.append({
                "type_id": grp["type_id"],
                "type_name": grp["type_name"],
                "total": grp["total"],
                "items": items_list,
            })
        currency_groups.sort(key=lambda x: x["total"], reverse=True)

        # 3. Discounts breakdown from DISCPARTS (DBSTATUS != -1) linked to closed PAYBINDINGS
        discounts_map = (master_data or {}).get("discounts", {})
        disc_groups = {}
        for dp in discparts:
            if dp.get("DBSTATUS") == "-1" or dp.get("SUM") is None:
                continue
            pb = paybinding_by_key.get((dp.get("VISIT"), dp.get("BINDINGUNI")))
            if not pb or pb.get("STATE") != "6":
                continue
            if selected_shift != "ALL":
                cl = currline_by_key.get((pb.get("VISIT"), pb.get("CURRUNI")))
                pc = check_by_key.get((pb.get("VISIT"), cl.get("CHECKUNI"))) if cl else None
                if not pc or not _check_in_scope(pc):
                    continue
            sifr = str(dp.get("SIFR") or "").strip()
            disc_obj = discounts_map.get(sifr) if sifr else None
            d_name = self._norm_text(disc_obj["name"]) if (disc_obj and disc_obj.get("name")) else f"Giảm giá #{sifr or 'khác'}"
            val = self._parse_int(dp.get("SUM"), 0) / 100
            if val == 0:
                continue
            d_entry = disc_groups.setdefault(sifr or d_name, {"sifr": sifr, "name": d_name, "sum": 0.0})
            d_entry["sum"] += val

        discount_items = sorted(disc_groups.values(), key=lambda x: abs(x["sum"]), reverse=True)
        discount_items_total = sum(d["sum"] for d in discount_items)

        # 4. Check & guest statistics
        unpaid_total = sum(self._parse_int(c.get("BINDEDSUM"), 0) for c in unpaid_checks) / 100
        unpaid_checks_count = len(unpaid_checks)
        unpaid_guests = 0
        seen_unpaid_visits = set()
        for c in unpaid_checks:
            if c.get("GUESTCNT") is not None:
                unpaid_guests += self._parse_int(c.get("GUESTCNT"), 0)
            else:
                v_id = c.get("VISIT")
                if v_id and v_id not in seen_unpaid_visits:
                    seen_unpaid_visits.add(v_id)
                    unpaid_guests += self._parse_int(orders_by_visit.get(v_id, {}).get("GUESTSCOUNT"), 0)

        paid_checks_count = len(closed_checks)
        paid_guests = sum(
            self._parse_int(
                c.get("GUESTCNT") if c.get("GUESTCNT") is not None else orders_by_visit.get(c.get("VISIT"), {}).get("GUESTSCOUNT"),
                0
            )
            for c in closed_checks
        )

        avg_guest = (total_paid / paid_guests) if paid_guests > 0 else 0.0
        avg_check = (total_paid / paid_checks_count) if paid_checks_count > 0 else 0.0

        # Begin/End print bill numbers
        print_nums = []
        for c in closed_checks:
            pn = resolve_check_print_number(c, printchecks, orders)
            if pn and str(pn).isdigit():
                print_nums.append(int(pn))
        begin_bill = min(print_nums) if print_nums else 0
        end_bill = max(print_nums) if print_nums else 0

        # Resolve header info for the selected shift
        shift_date = (selected_meta.get("shift_date") if selected_meta else "") or header.get("shift_date") or ""
        emp_id = selected_meta.get("manager_id") if selected_meta else ""
        if selected_shift == "ALL" and len(available_shifts) > 1:
            employee_name = "Tất cả ca"
        else:
            if not emp_id and closed_checks:
                emp_id = str(closed_checks[0].get("IAUTHOR") or "")
            employee_name = self._resolve_employee_display(emp_id, master_data) or "Hệ thống"
        restaurant_name = self._norm_text(header.get("restaurant_name"), f"Nhà hàng #{restaurant_id or '—'}")
        station_id = (selected_meta.get("station_id") if selected_meta else "") or header.get("station_id") or ""
        now_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

        shift_label = f"Ca #{selected_shift}" if selected_shift != "ALL" else "Tất cả ca trong file"

        # 5. Render 42-column thermal receipt preview matching CVL_baocaogiaocaTN.mak (FO.201)
        sep = "-" * 42
        k80_lines = [
            f"{'':30}{'FO.201':>12}",
            self._k80_center(restaurant_name),
            self._k80_center("BÁO CÁO GIAO CA THU NGÂN"),
            self._k80_center(f"Ngày: {shift_date or '—'}"),
            self._k80_center(f"Ca thu ngân: {selected_shift if selected_shift != 'ALL' else 'Tất cả'}"),
            self._k80_center(f"Nhân viên: {employee_name}"),
            f"{'Giờ in: ' + now_str:>42}",
            sep,
            self._k80_row("1. Tổng doanh thu", self._fmt_k80_amount(gross_revenue)),
            sep,
            self._k80_row(" 1.1 - Tổng giảm giá", self._fmt_k80_amount(total_discount)),
            self._k80_row(" 1.2 - Service Charge", "0"),
            self._k80_row(" 1.3 - VAT", self._fmt_k80_amount(vat_amount)),
            self._k80_row(" 1.4 - Tiền trước thuế", self._fmt_k80_amount(pre_tax_amount)),
            sep,
            "2. Doanh thu tiền tệ",
            sep,
        ]
        for grp in currency_groups:
            k80_lines.append(self._k80_row(f" - Doanh thu: {grp['type_name']}", self._fmt_k80_amount(grp["total"])))
            for item in grp["items"]:
                k80_lines.append(self._k80_row(f"     (+) {item['name']}", self._fmt_k80_amount(item["basic_sum"])))
        if not currency_groups:
            k80_lines.append(" (Không có giao dịch thanh toán)")

        k80_lines.extend([
            sep,
            "3. Thống kê",
            sep,
            self._k80_row(" 3.1 - Tổng chưa thanh toán", self._fmt_k80_amount(unpaid_total)),
            self._k80_row(" 3.2 - Số khách chưa thanh toán", str(unpaid_guests)),
            self._k80_row(" 3.3 - Số phiếu chưa thanh toán", str(unpaid_checks_count)),
            self._k80_row(" 3.4 - Tổng đã thanh toán", self._fmt_k80_amount(total_paid)),
            self._k80_row(" 3.5 - Số khách đã thanh toán", str(paid_guests)),
            self._k80_row(" 3.6 - Số phiếu đã thanh toán", str(paid_checks_count)),
            self._k80_row(" 3.7 - Giảm giá", self._fmt_k80_amount(discount_items_total if discount_items else total_discount)),
        ])
        for d_item in discount_items:
            k80_lines.append(self._k80_row(f"     - {d_item['name']}", self._fmt_k80_amount(d_item["sum"])))

        k80_lines.extend([
            self._k80_row(" 3.8 - TB Khách", self._fmt_k80_amount(avg_guest)),
            self._k80_row(" 3.9 - TB Phiếu", self._fmt_k80_amount(avg_check)),
            self._k80_row("Số bill đầu:", str(begin_bill)),
            self._k80_row("Số bill cuối:", str(end_bill)),
            sep,
            f"   {'Thu ngân':<26}{'Quản lý':>10}   ",
        ])

        return {
            "success": True,
            "selected_shift": selected_shift,
            "shift_label": shift_label,
            "available_shifts": available_shifts,
            "data_source": revenue_source,
            "stale_open_count": stale_open_count,
            "header": {
                "form_code": "FO.201",
                "title": "BÁO CÁO GIAO CA THU NGÂN",
                "restaurant_id": restaurant_id or "",
                "restaurant_name": restaurant_name,
                "shift_date": shift_date,
                "common_shift": target_common_shift,
                "cash_shift_num": selected_shift,
                "employee_id": emp_id,
                "employee_name": employee_name,
                "station_id": station_id,
                "generated_at": now_str,
                "has_master": bool(master_data),
                "master_display_name": header.get("master_display_name") or header.get("master_package") or "",
            },
            "revenue": {
                "gross_revenue": gross_revenue,
                "total_discount": total_discount,
                "service_charge": 0.0,
                "vat": vat_amount,
                "pre_tax": pre_tax_amount,
            },
            "currency_groups": currency_groups,
            "stats": {
                "unpaid_total": unpaid_total,
                "unpaid_guests": unpaid_guests,
                "unpaid_checks_count": unpaid_checks_count,
                "paid_total": total_paid,
                "paid_guests": paid_guests,
                "paid_checks_count": paid_checks_count,
                "discount_total": discount_items_total if discount_items else total_discount,
                "discount_items": discount_items,
                "avg_guest": avg_guest,
                "avg_check": avg_check,
                "begin_bill": begin_bill,
                "end_bill": end_bill,
            },
            "k80_text": "\n".join(k80_lines),
        }
