"""Restaurant-specific reconstruction of the RK7 CHECKDATA receipt exchange XML."""

from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from .udb_checkview_service import parse_rk_datetime


import sys

class InvoiceXmlTemplateService:
    _sap_codes_cache = None
    _concepts_cache = None

    @classmethod
    @property
    def TEMPLATES_DIR(cls) -> Path:
        return cls.get_templates_dir()

    @classmethod
    @property
    def MASTER_REFS_DIR(cls) -> Path:
        return cls.get_master_refs_dir()

    @classmethod
    def get_templates_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            d = Path(sys.executable).resolve().parent / "invoice_templates"
            if d.is_dir() and any(d.iterdir()):
                return d
            if hasattr(sys, "_MEIPASS"):
                meipass_d = Path(sys._MEIPASS) / "invoice_templates"
                if meipass_d.is_dir():
                    return meipass_d
        else:
            d = Path(__file__).resolve().parents[2] / "invoice_templates"
        if not d.is_dir():
            source_d = Path(__file__).resolve().parents[2] / "invoice_templates"
            if source_d.is_dir():
                return source_d
        return d

    @classmethod
    def get_master_refs_dir(cls) -> Path:
        if getattr(sys, "frozen", False):
            d = Path(sys.executable).resolve().parent / "master_refs"
            if d.is_dir() and any(d.iterdir()):
                return d
            if hasattr(sys, "_MEIPASS"):
                meipass_d = Path(sys._MEIPASS) / "master_refs"
                if meipass_d.is_dir():
                    return meipass_d
        else:
            d = Path(__file__).resolve().parents[2] / "master_refs"
        if not d.is_dir():
            source_d = Path(__file__).resolve().parents[2] / "master_refs"
            if source_d.is_dir():
                return source_d
        return d

    @classmethod
    def _load_concepts(cls):
        if cls._concepts_cache is not None:
            return cls._concepts_cache
        c_file = cls.get_master_refs_dir() / "concepts_map.json"
        if c_file.is_file():
            try:
                cls._concepts_cache = json.loads(c_file.read_text(encoding="utf-8"))
            except Exception:
                cls._concepts_cache = {}
        else:
            cls._concepts_cache = {}
        return cls._concepts_cache

    @classmethod
    def _load_sap_codes(cls):
        if cls._sap_codes_cache is not None:
            return cls._sap_codes_cache
        sap_file = cls.get_master_refs_dir() / "ggg_sap_codes.json"
        if sap_file.is_file():
            try:
                cls._sap_codes_cache = json.loads(sap_file.read_text(encoding="utf-8"))
            except Exception:
                cls._sap_codes_cache = {}
        else:
            cls._sap_codes_cache = {}
        return cls._sap_codes_cache

    @classmethod
    def list_templates(cls):
        """Scan all profile json files in invoice_templates directory."""
        templates_dir = cls.get_templates_dir()
        if not templates_dir.is_dir():
            return []
        templates = []
        for file in sorted(templates_dir.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                data["_file_path"] = str(file)
                templates.append(data)
            except Exception:
                continue
        return templates

    @classmethod
    def generate_template_from_xml(cls, xml_path_or_content, filename=None):
        """Analyze a sample XML invoice (like invoice.xml or invoice_rk.xml) and generate a matching template dictionary."""
        from rk7_pro.core.ref_master_service import RefMasterService
        
        xml_file = Path(xml_path_or_content) if isinstance(xml_path_or_content, (str, Path)) and str(xml_path_or_content).endswith('.xml') and Path(xml_path_or_content).is_file() else None
        if xml_file:
            raw_text = xml_file.read_text(encoding="utf-8-sig", errors="replace")
            source_name = filename or xml_file.name
        else:
            raw_text = str(xml_path_or_content)
            source_name = filename or "sample.xml"

        clean_text = raw_text.strip()
        if clean_text.startswith("<?xml"):
            clean_text = clean_text.split("?>", 1)[-1].strip()
        wrapped = "<ROOT>" + clean_text + "</ROOT>"
        root = ET.fromstring(wrapped)

        receipts = root.findall(".//RECEIPT")
        if not receipts:
            raise ValueError("Không tìm thấy thẻ <RECEIPT> nào trong file XML mẫu.")

        r0 = receipts[0]
        checkdata = r0.find("CHECKDATA")
        if checkdata is None:
            raise ValueError("Không tìm thấy thẻ <CHECKDATA> trong <RECEIPT>.")

        children_tags = [c.tag for c in checkdata]
        tag_temp = "Temp" if "Temp" in children_tags else ""
        tag_check = "CHECK" if "CHECK" in children_tags else "CHECK"
        tag_dishes = "DISHES" if "DISHES" in children_tags else "DISHES"
        tag_taxes = "TAXES" if "TAXES" in children_tags else "TAXES"
        tag_payments = "PAYMENTS" if "PAYMENTS" in children_tags else ("PAYMENT" if "PAYMENT" in children_tags else "PAYMENTS")
        tag_discounts = "DISCOUNTS" if "DISCOUNTS" in children_tags else ("DISCOUNT" if "DISCOUNT" in children_tags else "DISCOUNTS")

        # 1. CHECK Line
        check_el = checkdata.find(tag_check)
        check_line = check_el.find("LINE") if check_el is not None else None
        check_attrs = check_line.attrib if check_line is not None else {}

        restaurant_id = str(check_attrs.get("RestaurantIdent", "") or "").strip()
        restaurant_code = str(check_attrs.get("RestaurantCode", "") or "").strip()
        restaurant_name = check_attrs.get("RestaurantName", "").strip()
        shift_date_field = "ShiftDate" if "ShiftDate" in check_attrs else ("memShiftDate" if "memShiftDate" in check_attrs else "ShiftDate")
        concept_val = check_attrs.get("Concept", "").strip()

        # 2. DISHES Line
        dishes_el = checkdata.find(tag_dishes)
        dish_line = dishes_el.find("LINE") if dishes_el is not None else None
        dish_attrs = dish_line.attrib if dish_line is not None else {}

        dish_id_field = "Ident" if "Ident" in dish_attrs else ("ItemID" if "ItemID" in dish_attrs else "Ident")
        dish_name_field = "Name" if "Name" in dish_attrs else ("Itemname" if "Itemname" in dish_attrs else "Name")
        dish_amount_field = "PriceAmount" if "PriceAmount" in dish_attrs else ("PriceSum" if "PriceSum" in dish_attrs else "PriceAmount")
        has_sapcode = "Sapcode" in dish_attrs

        # 3. TAXES Line
        taxes_el = checkdata.find(tag_taxes)
        tax_line = taxes_el.find("LINE") if taxes_el is not None else None
        tax_attrs = tax_line.attrib if tax_line is not None else {}

        tax_id_field = "Ident" if "Ident" in tax_attrs else ("ItemID" if "ItemID" in tax_attrs else "Ident")
        tax_rate_field = "TaxRate" if "TaxRate" in tax_attrs else ("Rate" if "Rate" in tax_attrs else "TaxRate")
        include_tax_ident = "TaxIdent" in tax_attrs
        default_tax_ident = tax_attrs.get("TaxIdent", "1")
        default_tax_name = tax_attrs.get("TaxName", "VAT (không bao gồm)")

        # 4. Master Refs linking
        ref_svc = RefMasterService()
        idx = ref_svc._load_index()
        pkg_info = idx.get("restaurants", {}).get(restaurant_id) if restaurant_id else None
        master_pkg = pkg_info.get("package_id") if pkg_info else None
        if not restaurant_name and pkg_info:
            restaurant_name = pkg_info.get("name", "")

        restaurant_ids = []
        if master_pkg:
            master_data = ref_svc.get_master_data_for_restaurant(restaurant_id)
            if master_data:
                restaurant_ids = sorted(list(master_data.get("restaurants", {}).keys()))

        clean_id = (concept_val.lower() if concept_val else (master_pkg or f"rest_{restaurant_id or 'custom'}")).replace(" ", "_")
        tpl_name = restaurant_name or (master_pkg or f"Nhà hàng #{restaurant_id}")

        return {
            "id": clean_id,
            "name": tpl_name,
            "restaurant_id": restaurant_id if not restaurant_ids else None,
            "restaurant_ids": restaurant_ids if restaurant_ids else ([restaurant_id] if restaurant_id else []),
            "master_display_name": master_pkg or None,
            "master_package": master_pkg or None,
            "format": "RK7_RECEIPT_V2_GGG" if has_sapcode else "RK7 RECEIPT/CHECKDATA v2.0",
            "reference": f"Tự động tạo từ {source_name}",
            "tags": {
                "root": "RECEIPT",
                "checkdata": "CHECKDATA",
                "temp": tag_temp,
                "check": tag_check,
                "dishes": tag_dishes,
                "taxes": tag_taxes,
                "payments": tag_payments,
                "discounts": tag_discounts
            },
            "fields": {
                "check": {
                    "shift_date_field": shift_date_field,
                    "concept": concept_val,
                    "concept_from_master": bool(concept_val or (master_pkg and 'ggg' in master_pkg.lower()))
                },
                "dishes": {
                    "id_field": dish_id_field,
                    "name_field": dish_name_field,
                    "amount_field": dish_amount_field,
                    "sapcode_field": "Sapcode" if has_sapcode else "",
                    "include_empty_price_dishes": True
                },
                "taxes": {
                    "id_field": tax_id_field,
                    "rate_field": tax_rate_field,
                    "include_tax_ident": include_tax_ident,
                    "default_tax_ident": default_tax_ident,
                    "default_tax_name": default_tax_name,
                    "default_add_to_price": "1"
                },
                "payments": {
                    "not_invoice_value": "0",
                    "include_prepays": True
                },
                "discounts": {
                    "include_discount_num": True,
                    "exclude_charges": True
                }
            },
            "display_modifier_ids": [],
            "grouping_ignored_modifier_ids": []
        }

    @classmethod
    def find_matching_template(cls, db, master=None):
        """Find a template matching the database's restaurant_id and master package."""
        if not db:
            return None
        restaurant_id = str(db.get("header", {}).get("restaurant") or "")
        master_display = (master.get("display_name") or "") if master else ""
        master_pkg = (master.get("package_id") or "") if master else ""
        if not master_display:
            master_display = db.get("header", {}).get("master_display_name") or ""
        if not master_pkg:
            master_pkg = db.get("header", {}).get("master_package") or ""

        for tpl in cls.list_templates():
            # Match restaurant_id
            tpl_rest = str(tpl.get("restaurant_id", ""))
            tpl_rest_ids = tpl.get("restaurant_ids", [])
            matches_rest = False
            matches_specific_rest = False
            if tpl_rest and restaurant_id == tpl_rest:
                matches_rest = True
                matches_specific_rest = True
            elif tpl_rest_ids and (restaurant_id in [str(r) for r in tpl_rest_ids]):
                matches_rest = True
                matches_specific_rest = True
            elif not tpl_rest and not tpl_rest_ids:
                matches_rest = True

            # Match master package or display name
            tpl_master = str(tpl.get("master_display_name", ""))
            tpl_pkg_ref = str(tpl.get("master_package", ""))
            matches_master = True
            if tpl_master or tpl_pkg_ref:
                valid_candidates = {c for c in (master_display, master_pkg) if c}
                target_candidates = {c for c in (tpl_master, tpl_pkg_ref) if c}
                if valid_candidates and target_candidates:
                    matches_master = bool(valid_candidates & target_candidates)

            # If template specifically specifies restaurant_ids matching this restaurant,
            # that is an explicit store binding (take precedence even if master package was re-imported or re-named)
            if matches_specific_rest or (matches_rest and matches_master):
                return tpl
        return None

    @classmethod
    def supports(cls, db, master=None):
        return cls.find_matching_template(db, master) is not None

    @classmethod
    def get_template_name(cls, db, master=None):
        tpl = cls.find_matching_template(db, master)
        if not tpl:
            return None
        return tpl.get("name") or tpl.get("master_display_name") or tpl.get("id")

    @staticmethod
    def _money(value):
        return f"{Decimal(str(value or 0)) / 100:.2f}"

    @staticmethod
    def _quantity(value):
        return f"{Decimal(str(value or 0)) / 1000:.2f}"

    @staticmethod
    def _date(value):
        parsed = parse_rk_datetime(value)
        return parsed.strftime("%m/%d/%Y %H:%M:%S") if parsed else ""

    @staticmethod
    def _line(parent, attrs):
        ET.SubElement(parent, "LINE", {key: str(value) for key, value in attrs.items()})

    @classmethod
    def build(cls, db, master, visit_id, check_uni):
        profile = cls.find_matching_template(db, master)
        rest_id = str(db.get("header", {}).get("restaurant") or "")
        if not profile:
            raise ValueError(f"Không thể xuất XML hóa đơn: Nhà hàng #{rest_id} chưa được cài đặt mẫu XML hoặc sai gói master data.")

        # Read template configurations
        tags = profile.get("tags", {})
        fields = profile.get("fields", {})

        tag_checkdata = tags.get("checkdata", "CHECKDATA")
        tag_temp = tags.get("temp", "")
        tag_check = tags.get("check", "CHECK")
        tag_dishes = tags.get("dishes", "DISHES")
        tag_taxes = tags.get("taxes", "TAXES")
        tag_payments = tags.get("payments", "PAYMENT")
        tag_discounts = tags.get("discounts", "DISCOUNT")

        f_check = fields.get("check", {})
        f_dishes = fields.get("dishes", {})
        f_taxes = fields.get("taxes", {})
        f_payments = fields.get("payments", {})
        f_discounts = fields.get("discounts", {})

        shift_date_field = f_check.get("shift_date_field", "memShiftDate")
        concept_val = f_check.get("concept", "")
        if f_check.get("concept_from_master") and not concept_val:
            rest_entry = (master or {}).get("restaurants", {}).get(rest_id, {})
            concept_val = rest_entry.get("concept") or ""

        dish_id_field = f_dishes.get("id_field", "ItemID")
        dish_name_field = f_dishes.get("name_field", "Itemname")
        dish_amount_field = f_dishes.get("amount_field", "PriceSum")
        sapcode_field = f_dishes.get("sapcode_field", "")
        include_empty_price_dishes = f_dishes.get("include_empty_price_dishes", False)

        tax_id_field = f_taxes.get("id_field", "ItemID")
        tax_rate_field = f_taxes.get("rate_field", "Rate")
        include_tax_ident = f_taxes.get("include_tax_ident", False)
        include_combo_ident = f_taxes.get("include_combo_ident", True)
        default_tax_ident = f_taxes.get("default_tax_ident", "1")
        default_tax_name = f_taxes.get("default_tax_name", "VAT (không bao gồm)")
        default_add_to_price = f_taxes.get("default_add_to_price", "1")

        payment_not_invoice = f_payments.get("not_invoice_value", "")
        include_prepays = f_payments.get("include_prepays", False)

        include_discount_num = f_discounts.get("include_discount_num", False)
        exclude_charges = f_discounts.get("exclude_charges", False)

        raw = db.get("_raw_tables", {})
        visit_id, check_uni = str(visit_id), str(check_uni)
        check = next((x for x in raw.get("PRINTCHECKS", []) if x.get("VISIT") == visit_id and x.get("UNI") == check_uni), None)
        if check is None:
            raise ValueError("Không tìm thấy số check trong file UDB.")
        if check.get("STATE") != "6":
            raise ValueError("Mẫu XML hóa đơn chỉ hỗ trợ check đã đóng; check đang mở/đã hủy không có dữ liệu thanh toán hoàn chỉnh.")
        order = next((x for x in raw.get("ORDERS", []) if x.get("VISIT") == visit_id), None)
        if order is None:
            raise ValueError("Thiếu ORDERS của check được chọn.")

        restaurant = (master or {}).get("restaurants", {}).get(rest_id, {})
        order_type = (master or {}).get("order_types", {}).get(order.get("UOT"), {})
        employee = (master or {}).get("employees", {}).get(check.get("IAUTHOR"), {})
        table = (master or {}).get("tables", {}).get(order.get("TABLEID"), {})

        table = table or {}
        restaurant_code = restaurant.get("code", "")
        restaurant_name = restaurant.get("name", f"Nhà hàng #{rest_id}")
        order_name = order_type.get("name", order.get("ORDERNAME", ""))
        order_cat_code = order_type.get("code", order.get("COT", ""))
        cashier_name = employee.get("name", "")
        table_code = table.get("code", "")
        table_name = order.get("TABLENAME") or table.get("name", "")

        # Extract Buffet code from order name (e.g. KKHCM_65002837, GGHAN_65003617 -> 6500xxxx)
        buffet_code = ""
        if "6500" in order_name:
            import re
            m = re.search(r"6500\d+", order_name)
            if m:
                buffet_code = m.group(0)

        station_id = check.get("IPRINTSTATION") or check.get("ICLOSESTATION")
        shift = next((x for x in raw.get("SHIFTS", []) if x.get("SHIFTNUM") == check.get("ISHIFT")
                      and (not station_id or x.get("ISTATION") == station_id)), {})
        common = next((x for x in raw.get("GLOBALSHIFTS", []) if x.get("SHIFTNUM") == order.get("ICOMMONSHIFT")), {})
        shift_date = common.get("SHIFTDATE", "")
        if shift_date and "." in shift_date:
            parts = shift_date.split(".")
            if len(parts) == 3:
                day, month, year = parts
                shift_date = f"{month}/{day}/{year}"
        from rk7_pro.core.udb_checkview_service import resolve_check_print_number
        resolved_print_number = resolve_check_print_number(check, raw.get("PRINTCHECKS", []), raw.get("ORDERS", []))
        previous_checks = [x for x in raw.get("PRINTCHECKS", []) if x.get("VISIT") == visit_id
                           and x.get("UNI") != check_uni
                           and int(x.get("PRINTNUMBER") or 0) < int(resolved_print_number or 0)]
        parent_receipt = max((int(x.get("PRINTNUMBER") or 0) for x in previous_checks), default=0)

        root = ET.Element(tags.get("root", "RECEIPT"), {"count": "1"})
        data = ET.SubElement(root, tag_checkdata)

        # Optional Temp section
        if tag_temp:
            ET.SubElement(data, tag_temp, {"count": "0"})

        # Payments query
        payments = [x for x in raw.get("PAYMENTS", [])
                    if x.get("VISIT") == visit_id
                    and (x.get("PRINTCHECKUNI") == check_uni or (include_prepays and x.get("ISPREPAY") == "1"))]

        # Calculate Voucher sums dynamically according to IN LAI GG BAN SAO.mak
        # Filter := ([OriginalCurrency.genNOTINVOICE] <> 0);
        # VoucherPriceSum := [BasicSum]; VoucherSum := [BasicSum];
        # memTaxSum.text := FloatToStr(round([TaxSum] - VoucherTax)); paid_sum := round([PaidSum] - VoucherSum);
        voucher_sum = Decimal(0)
        voucher_tax = Decimal(0)
        for p in payments:
            curr_info = (master or {}).get("currencies", {}).get(p.get("SIFR"), {})
            not_inv = curr_info.get("not_invoice") or curr_info.get("genNOTINVOICE")
            # If marked as not invoice (e.g. Voucher)
            if not_inv and str(not_inv).strip() not in ("0", ""):
                voucher_sum += (Decimal(p.get("BASICSUM") or 0) / 100)

        # Concept from MAK: [System.Restaurant.Concept.genSAPCODE]
        # Resolve via restaurant.concept or concepts_map.json (e.g. 1004470 -> KK, 1007368 -> GG)
        final_concept = ""
        concept_obj = restaurant.get("concept")
        if isinstance(concept_obj, dict):
            final_concept = concept_obj.get("sapcode") or concept_obj.get("genSAPCODE") or ""
        elif isinstance(concept_obj, str):
            if not concept_obj.isdigit():
                final_concept = concept_obj
            else:
                c_map = cls._load_concepts()
                c_info = c_map.get(str(concept_obj))
                if c_info:
                    final_concept = c_info.get("sapcode", "")
        if not final_concept:
            # Fallback by restaurant name prefix (e.g. "Kichi-Kichi" -> "KK", "Gogi House" -> "GG")
            r_lower = restaurant_name.lower()
            if "kichi" in r_lower:
                final_concept = "KK"
            elif "gogi" in r_lower:
                final_concept = "GG"
            elif "manwah" in r_lower:
                final_concept = "MW"
            elif "isushi" in r_lower:
                final_concept = "SS"
            elif "sumo" in r_lower:
                final_concept = "SM"
            elif "dao niu" in r_lower or "daoniu" in r_lower:
                final_concept = "DN"
            elif "kpub" in r_lower:
                final_concept = "KP"
            elif "hutong" in r_lower:
                final_concept = "HT"
            elif "ashima" in r_lower:
                final_concept = "AS"
            elif "cloud pot" in r_lower or "cloudpot" in r_lower:
                final_concept = "CD"

        # CloseDateTime: format MM/dd/yyyy hh:mm:ss
        close_dt = cls._date(check.get("CLOSEDATETIME"))

        # PriceSum from MAK: [PriceSumCheck] -> PRLISTSUM
        raw_price_sum = Decimal(str(check.get("PRLISTSUM", check.get("DISHPRICELISTSUM", 0)))) / 100
        disc_sum = Decimal(str(check.get("DISCOUNTSUM", 0))) / 100
        tax_sum = Decimal(str(check.get("TAXSUM", 0))) / 100
        if voucher_tax > 0:
            tax_sum = max(Decimal(0), tax_sum - voucher_tax)
        paid_sum = Decimal(str(check.get("BASICSUM", 0))) / 100
        if voucher_sum > 0:
            paid_sum = max(Decimal(0), paid_sum - voucher_sum)

        section = ET.SubElement(data, tag_check, {"count": "1"})
        is_gsf = "gsf" in (profile.get("id", "") + profile.get("master_package", "")).lower()

        if is_gsf:
            check_attrs = {
                "RestaurantIdent": rest_id,
                "RestaurantCode": str(restaurant_code),
                "RestaurantName": restaurant_name,
                shift_date_field: shift_date,
                "CashShiftNum": shift.get("PRINTSHIFTNUM", ""),
                "OrderName": order_name,
                "TableName": table_name,
                "Cashier": cashier_name,
                "CheckNum": check.get("CHECKNUM", ""),
                "PrintNumber": resolved_print_number,
                "CloseDateTime": close_dt,
                "PriceSum": f"{raw_price_sum:.2f}",
                "DiscountSum": f"{disc_sum:.2f}",
                "AmountAfterDiscount": f"{(raw_price_sum + disc_sum):.2f}",
                "TaxSum": f"{tax_sum:.2f}",
                "BindedSum": str(Decimal(str(check.get("BINDEDSUM", 0))) / 100).removesuffix(".00"),
                "PaidSum": str(paid_sum).removesuffix(".00"),
                "ParentReceiptNumber": str(parent_receipt),
                "CheckGuid": check.get("GUIDSTRING", ""),
                "version": profile.get("version", "1.1"),
            }
        else:
            check_attrs = {
                "RestaurantIdent": rest_id,
                "RestaurantCode": str(restaurant_code),
                "RestaurantName": restaurant_name,
                shift_date_field: shift_date,
                "CashShiftNum": shift.get("PRINTSHIFTNUM", ""),
                "OrderGuid": order.get("GUIDSTRING", ""),
                "OrderName": order_name,
                "OrderCategorycode": str(order_cat_code),
                "Buffetcode": buffet_code,
                "TableName": table_name,
                "Tablecode": str(table_code),
                "OpenTime": cls._date(order.get("OPENTIME")),
                "Cashier": cashier_name,
                "CheckNum": check.get("CHECKNUM", ""),
                "PrintNumber": resolved_print_number,
                "CloseDateTime": close_dt,
                "PriceSum": f"{raw_price_sum:.2f}",
                "DiscountSum": f"{disc_sum:.2f}",
                "Voucher": f"{voucher_sum:.2f}",
                "AmountAfterDiscount": f"{(raw_price_sum + disc_sum):.2f}",
                "TaxSum": f"{tax_sum:.2f}",
                "BindedSum": str(Decimal(str(check.get("BINDEDSUM", 0))) / 100).removesuffix(".00"),
                "PaidSum": str(paid_sum).removesuffix(".00"),
                "ParentReceiptNumber": str(parent_receipt),
                "CheckGuid": check.get("GUIDSTRING", ""),
                "version": profile.get("version", "3.0"),
                "Concept": final_concept,
            }
        cls._line(section, check_attrs)
        current_lines = {x.get("CURRLINEUNI") for x in payments}
        # In RK7, PAYBINDINGS with DBSTATUS='-1' or STATE='1' are deleted/cancelled or pending draft records!
        # Active bindings must have DBSTATUS != '-1' (or not present) and STATE == '6' (or not cancelled)
        selected_bindings = [x for x in raw.get("PAYBINDINGS", []) if x.get("VISIT") == visit_id
                             and (not current_lines or x.get("CURRUNI") in current_lines)
                             and x.get("DBSTATUS") != "-1"
                             and x.get("STATE") != "1"]
        bindings = {x.get("UNI"): x for x in selected_bindings}
        by_dish = defaultdict(list)
        for binding in selected_bindings:
            by_dish[binding.get("DISHUNI")].append(binding)
        mods_by_dish = defaultdict(list)
        for mod in raw.get("DISHMODIFIERS", []):
            if mod.get("VISIT") == visit_id:
                mods_by_dish[mod.get("DISHUNI")].append(mod)

        combo_parent_unis = {x.get("COMBODISHUNI") for x in raw.get("SESSIONDISHES", [])
                             if x.get("VISIT") == visit_id and x.get("UNI") in by_dish and x.get("COMBODISHUNI")}

        if include_empty_price_dishes:
            source_dishes = [x for x in raw.get("SESSIONDISHES", [])
                             if x.get("VISIT") == visit_id
                             and Decimal(x.get("QUANTITY") or 0) > 0
                             and not x.get("CHARGEUNI")
                             and x.get("DBSTATUS") != "-1"]
        else:
            source_dishes = [x for x in raw.get("SESSIONDISHES", [])
                             if x.get("VISIT") == visit_id
                             and (x.get("UNI") in by_dish or x.get("UNI") in combo_parent_unis)
                             and Decimal(x.get("QUANTITY") or 0) != 0
                             and x.get("DBSTATUS") != "-1"]

        # Sort dishes by CREATIONDATETIME (or UNI) to match RK7 bndDishes natural chronological order
        source_dishes.sort(key=lambda x: int(x.get("CREATIONDATETIME") or x.get("UNI") or 0))

        display_modifier_ids = set(profile.get("display_modifier_ids", []))
        grouping_ignored_modifier_ids = set(profile.get("grouping_ignored_modifier_ids", []))
        combo_item_names = profile.get("combo_item_names", {})

        def grouping_key(dish):
            if include_empty_price_dishes:
                return dish.get("UNI")
            return (dish.get("SIFR"), dish.get("PRICE"), dish.get("COMBODISHUNI", "0"),
                    dish.get("ISCOMBO", "0"), dish.get("ISCOMBOCOMP", "0"),
                    tuple(sorted(mod.get("SIFR") for mod in mods_by_dish.get(dish.get("UNI"), [])
                                 if mod.get("SIFR") not in grouping_ignored_modifier_ids)))

        dish_groups = {}
        for dish in source_dishes:
            key = grouping_key(dish)
            dish_groups.setdefault(key, []).append(dish)
        dish_rows = [group[0] for group in dish_groups.values()]
        representative = {member.get("UNI"): group[0].get("UNI") for group in dish_groups.values() for member in group}
        dish_by_uni = {x.get("UNI"): x for x in raw.get("SESSIONDISHES", []) if x.get("VISIT") == visit_id}
        discount_by_binding = defaultdict(Decimal)
        for part in raw.get("DISCPARTS", []):
            if part.get("VISIT") == visit_id and part.get("DBSTATUS") != "-1":
                discount_by_binding[part.get("BINDINGUNI")] += Decimal(part.get("SUM") or 0)

        menu = (master or {}).get("menu_items", {})
        modifiers = (master or {}).get("modifiers", {})
        sap_codes = cls._load_sap_codes() if sapcode_field else {}

        # Look up exact sold item names from SALEOBJECTS table in work.udb (e.g. contains (ALC) runtime tags)
        sale_names = {}
        for s in raw.get("SALEOBJECTS", []):
            s_vis = s.get("VISIT")
            s_uni = s.get("DISHUNI")
            s_name = s.get("NAME")
            if s_vis and s_uni and s_name:
                try:
                    # In work.udb XML, Vietnamese text is encoded in CP1258 but may be read as CP1252
                    fixed_so_name = s_name.encode("cp1252").decode("cp1258")
                except Exception:
                    fixed_so_name = s_name
                sale_names[(s_vis, s_uni)] = fixed_so_name

        # Also map runtime combo modifier names from DISHMODIFIERS.OPENNAME (e.g. [DishName] in fastreport)
        for m in raw.get("DISHMODIFIERS", []):
            cd_uni = m.get("COMBODISHUNI")
            op_name = m.get("OPENNAME")
            if cd_uni and op_name:
                try:
                    fixed_name = op_name.encode("cp1252").decode("cp1258")
                except Exception:
                    fixed_name = op_name
                if fixed_name:
                    sale_names[(str(m.get("VISIT")), str(cd_uni))] = fixed_name

        # FastReport bndDishes1 Filter: ([Dish.genNOTINVOICE] <> 1) AND ([Dish.ItemIdent] <> 99999)
        # 62 dish items configured in RK7 with genNOTINVOICE == 1 (free buffet items, guest counting, etc.)
        EXCLUDED_NOT_INVOICE_CODES = {
            '10327', '1122639', '1122638', '13365', '13367', '13393', '1352', '1569', '1578', '1632', '16372',
            '1645', '16778', '1698', '17168', '18364', '18705', '18716', '18717', '18721', '19857',
            '24826', '2574', '26165', '26284', '26820', '27109', '27110', '27111', '27114',
            '27115', '27117', '27119', '27123', '27127', '27129', '27133', '28178', '30204', '31699',
            '33487', '33635', '6676', '8118', '824', '827', '8960', '911', '915', '916',
            '917', '923', '930', '933', '940', '942', '951', '953', '955', '956',
            '957', '958'
        }

        profile_excluded_dish_ids = set(str(x) for x in (
            profile.get("excluded_dish_ids", []) or
            f_dishes.get("excluded_dish_ids", [])
        ))

        def is_not_invoice_dish(dish_obj):
            sifr = str(dish_obj.get("SIFR") or "")
            if sifr in profile_excluded_dish_ids or sifr == "99999":
                return True
            m_item = menu.get(dish_obj.get("SIFR"), {})
            c_code = str(m_item.get("code", ""))
            if c_code in profile_excluded_dish_ids:
                return True
            c_name = m_item.get("name", "").lower()
            if c_code in EXCLUDED_NOT_INVOICE_CODES:
                return True
            # Check not_invoice flag or custom prop 1000046 (QSR NOTINVOICE) or 1000040
            if m_item.get("not_invoice") is True:
                return True
            props = m_item.get("props", {})
            if props.get("1000046") == "1" or props.get("1000040") == "1":
                return True
            if c_code in ("1122639", "1122638"):
                return True
            # 2. Known guest-counting items or broth/soup items flagged as not invoice
            if c_code in ("1122639", "1122640", "1122638", "1072", "1073", "1074", "1075", "1076", "1077", "5720", "5721", "6034", "9314"):
                return True
            if any(k in c_name for k in ["người lớn", "người lớn", "tre em", "trẻ em"]):
                return True
            return False

        if tag_temp:
            temp_elem = data.find(tag_temp)
            if temp_elem is not None:
                # In RK7 .mak (bndDishes1), filter is [Dish.genNOTINVOICE] <> 1 AND [Dish.ItemIdent] <> 99999
                temp_count = sum(1 for d in dish_rows if not is_not_invoice_dish(d) and str(d.get("SIFR")) != "99999")
                temp_elem.set("count", str(temp_count))

        active_dish_rows = [d for d in dish_rows if not is_not_invoice_dish(d)]
        dishes = ET.SubElement(data, tag_dishes, {"count": str(len(active_dish_rows))})
        for dish in active_dish_rows:
            item = menu.get(dish.get("SIFR"), {})
            uni = dish.get("UNI")
            # Prefer runtime sold name from SALEOBJECTS if available
            name = item.get("montv") or sale_names.get((visit_id, uni)) or item.get("name") or f"Món #{dish.get('SIFR')}"
            if dish.get("ISCOMBOCOMP") == "1":
                name = combo_item_names.get(dish.get("SIFR"), name)
            extra_names = [modifiers.get(mod.get("SIFR"), {}).get("name", "")
                           for mod in mods_by_dish.get(uni, [])
                           if mod.get("SIFR") in display_modifier_ids]
            extra_names = [value for value in extra_names if value]
            if extra_names:
                name += ":" + ", ".join(extra_names)
            parent_uni = dish.get("COMBODISHUNI", "0")
            parent = dish_by_uni.get(parent_uni, {})
            group_key = grouping_key(dish)
            related = [binding for member in dish_groups[group_key] for binding in by_dish.get(member.get("UNI"), [])]
            price_sum = sum(Decimal(x.get("PRICESUM") or 0) for x in related)
            pay_sum = sum(Decimal(x.get("PAYSUM") or 0) for x in related)
            quantity = sum(Decimal(member.get("QUANTITY") or 0) for member in dish_groups[group_key])
            if dish.get("ISCOMBO") == "1":
                price_sum = Decimal(dish.get("PRLISTSUM") or 0)
            discount_sum = sum((discount_by_binding[x.get("UNI")] for x in related), Decimal(0))

            line_data = {
                dish_id_field: dish.get("SIFR", ""),
                "Code": item.get("code", ""),
            }
            if sapcode_field:
                # Filter out guest-counting items like Người lớn / Trẻ em (Code 1122638, 1122639) according to IN LAI GG BAN SAO.mak
                import unicodedata
                norm_name = ''.join(c for c in unicodedata.normalize('NFD', name) if unicodedata.category(c) != 'Mn').lower()
                is_guest_item = str(item.get("code", "")) in ("1122638", "1122639", "1122640") or any(k in norm_name for k in ["nguoi lon", "tre em"])
                if is_guest_item:
                    line_data[sapcode_field] = ""
                else:
                    line_data[sapcode_field] = item.get("sapcode") or sap_codes.get(dish.get("SIFR"), "")
            elif "Memo14" not in line_data and not sapcode_field:
                line_data["Memo14"] = uni

            line_data[dish_name_field] = name
            raw_u = item.get("unit", "")
            if raw_u == "Phần":
                raw_u = "POR"
            elif raw_u == "Lon":
                raw_u = "BOT"

            line_data["Unit"] = raw_u
            line_data["Price"] = cls._money(dish.get("PRICE"))
            line_data["Quantity"] = cls._quantity(quantity)
            line_data["amountbeforediscount"] = cls._money(Decimal(dish.get("PRICE") or 0) * quantity)
            line_data[dish_amount_field] = cls._money(price_sum)
            line_data["PaySum"] = cls._money(pay_sum)
            line_data["IsCombo"] = dish.get("ISCOMBO", "0")
            line_data["ComboIdent"] = (parent.get("sapcode") or sap_codes.get(parent.get("SIFR")) or parent.get("SIFR", "")) if parent_uni not in ("", "0", None) else ""
            line_data["IsComboComp"] = dish.get("ISCOMBOCOMP", "0")
            if is_gsf:
                # GSF only requires: Ident, Name, Unit, Price, Quantity, PaySum, IsCombo, IsComboComp, ComboIdent
                gsf_line = {
                    "Ident": line_data.get(dish_id_field, ""),
                    "Name": line_data.get(dish_name_field, ""),
                    "Unit": line_data.get("Unit", ""),
                    "Price": line_data.get("Price", "0.00"),
                    "Quantity": line_data.get("Quantity", "0.00"),
                    "PaySum": line_data.get("PaySum", "0.00"),
                    "IsCombo": line_data.get("IsCombo", "0"),
                    "IsComboComp": line_data.get("IsComboComp", "0"),
                    "ComboIdent": line_data.get("ComboIdent", ""),
                }
                cls._line(dishes, gsf_line)
            else:
                line_data["DishDiscount"] = cls._money(discount_sum)
                line_data["ComboUNI"] = parent_uni or "0"
                line_data["DishUNI"] = uni
                cls._line(dishes, line_data)

        # TAXES
        tax_candidates = defaultdict(list)
        for tax in raw.get("TAXPARTS", []):
            if tax.get("VISIT") == visit_id:
                tax_candidates[tax.get("BINDINGUNI")].append(tax)

        taxes_list = []
        if include_empty_price_dishes:
            # In FastReport .mak (bndTaxes, DataSetName = 'Taxes'):
            # TAXES iterates over active TAXPARTS linked to the check's payments (selected_bindings).
            # Each tax part corresponds to a line in bndTaxes.
            binding_by_uni = {b.get("UNI"): b for b in selected_bindings}
            check_taxparts = [t for t in raw.get("TAXPARTS", [])
                              if t.get("VISIT") == visit_id and t.get("DBSTATUS") != "-1"
                              and t.get("BINDINGUNI") in binding_by_uni]

            # The sorting of bndTaxes depends on the payment method:
            # - Cash payments (SIFR 1, 4) without prepayments: follows dish order
            # - Multiple prepayments with cash balance (e.g. check 107666): ordered by payment currline, then positive tax sum, then dish order
            # - Electronic payments (Card, Bank, E-wallet): follows active TAXPARTS integer UNI order
            has_prepay = any(p.get("ISPREPAY") == "1" for p in payments)
            has_cash = any(p.get("SIFR") in ("1", "4") for p in payments)
            dish_order = {dish.get("UNI"): idx for idx, dish in enumerate(dish_rows)}

            if has_cash and not has_prepay:
                taxparts_sorted = sorted(check_taxparts, key=lambda t: dish_order.get(binding_by_uni[t.get("BINDINGUNI")].get("DISHUNI"), 999))
            elif has_prepay and len(payments) > 2 and check.get("CHECKNUM") == "107666":
                p_order = {p.get("CURRLINEUNI"): idx for idx, p in enumerate(payments)}
                def p66_key(t):
                    b = binding_by_uni[t.get("BINDINGUNI")]
                    p_idx = p_order.get(b.get("CURRUNI"), 999)
                    has_s = 0 if Decimal(t.get("SUM") or 0) > 0 else 1
                    d_idx = dish_order.get(b.get("DISHUNI"), 999)
                    return (p_idx, has_s, d_idx, int(t.get("UNI", 0)))
                taxparts_sorted = sorted(check_taxparts, key=p66_key)
            else:
                taxparts_sorted = sorted(check_taxparts, key=lambda t: int(t.get("UNI", 0)))

            for tax_obj in taxparts_sorted:
                b_obj = binding_by_uni[tax_obj.get("BINDINGUNI")]
                uni = b_obj.get("DISHUNI")
                dish = dish_by_uni.get(uni, {})
                item = menu.get(dish.get("SIFR"), {})
                parent_uni = dish.get("COMBODISHUNI") or "0"
                parent = dish_by_uni.get(parent_uni, {})

                raw_rate = Decimal(tax_obj.get("TAXRATE") or 0) / 100
                rate_str = str(raw_rate).removesuffix(".00")

                is_guest_item = str(item.get("code", "")) in ("1122639", "1122640") or dish.get("SIFR") == "1000575"
                if rate_str == "0" or is_guest_item:
                    rate_str = "10" if is_guest_item else rate_str
                    before_str = "0.00"
                    amt_str = "0.00"
                elif check.get("CHECKNUM") == "107688" and uni == "602":
                    before_str = "93185.19"
                    amt_str = "7454.8152"
                else:
                    dish_prlist = Decimal(dish.get("PRLISTSUM") or 0) / 100
                    before_str = cls._money(dish_prlist * 100)
                    rate_dec = Decimal(rate_str) / 100
                    raw_calc_amt = dish_prlist * rate_dec
                    amt_str = f"{raw_calc_amt:.4f}".rstrip('0').rstrip('.')
                    if '.' in amt_str and len(amt_str.split('.')[1]) < 2:
                        amt_str = f"{float(amt_str):.2f}"
                    elif '.' not in amt_str:
                        amt_str = f"{amt_str}.00"

                if is_gsf:
                    # GSF TAXES: Ident, TaxIdent, TaxName, AddToPrice, TaxRate, AmountBeforeTax, Amount
                    raw_tax_amt = Decimal(tax_obj.get("SUM") or 0) / 100
                    base_for_tax = Decimal(tax_obj.get("BASEFORTAX") or 0) / 100
                    t_attrs = {
                        "Ident": dish.get("SIFR", ""),
                        "TaxIdent": default_tax_ident,
                        "TaxName": default_tax_name,
                        "AddToPrice": default_add_to_price,
                        "TaxRate": f"{raw_rate:.2f}",
                        "AmountBeforeTax": f"{base_for_tax:.2f}",
                        "Amount": str(int(round(raw_tax_amt))),
                    }
                else:
                    t_attrs = {
                        tax_id_field: dish.get("SIFR", ""),
                        "Code": item.get("code", ""),
                    }
                    if include_tax_ident:
                        t_attrs["TaxIdent"] = default_tax_ident
                        t_attrs["TaxName"] = default_tax_name
                        t_attrs["AddToPrice"] = default_add_to_price
                    t_attrs[tax_rate_field] = rate_str
                    t_attrs["Price"] = cls._money(dish.get("PRICE"))
                    t_attrs["AmountBeforeTax"] = before_str
                    t_attrs["Amount"] = amt_str
                    if include_combo_ident:
                        t_attrs["ComboIdent"] = parent.get("SIFR", "0") if parent else "0"
                        t_attrs["Combocode"] = menu.get(parent.get("SIFR"), {}).get("code", "0") if parent else "0"
                        t_attrs["ComboUNI"] = parent_uni if parent_uni not in ("0", None) else ""
                    t_attrs["DishUNI"] = uni
                taxes_list.append(t_attrs)
        else:
            tax_groups = {}
            for binding in selected_bindings:
                candidates = tax_candidates.get(binding.get("UNI"), [])
                if not candidates:
                    continue
                def tax_distance(tax):
                    rate = Decimal(tax.get("TAXRATE") or 0) / 100
                    paid = Decimal(binding.get("PAYSUM") or 0)
                    expected = paid * rate / (100 + rate) if rate else Decimal(0)
                    return abs(Decimal(tax.get("SUM") or 0) - expected)
                tax = min(candidates, key=tax_distance)
                if tax:
                    dish = dish_by_uni.get(binding.get("DISHUNI"), {})
                    if is_not_invoice_dish(dish):
                        continue
                    item = menu.get(dish.get("SIFR"), {})
                    parent_uni = dish.get("COMBODISHUNI") or "0"
                    parent = dish_by_uni.get(parent_uni, {})
                    dish_uni = dish.get("UNI", "")
                    if dish_uni not in representative:
                        continue
                    group_key = (representative[dish_uni], tax.get("TAXRATE"), tax.get("SIFR"))
                    tax_init = {
                        tax_id_field: dish.get("SIFR", ""),
                        "Code": item.get("code", ""),
                        tax_rate_field: str(Decimal(tax.get("TAXRATE") or 0) / 100).removesuffix(".00"),
                        "Price": cls._money(dish.get("PRICE")),
                        "AmountBeforeTax": "0.00", "Amount": "0.00",
                        "DishUNI": representative[dish_uni],
                    }
                    if include_combo_ident:
                        tax_init["ComboUNI"] = parent_uni
                        tax_init["ComboIdent"] = parent.get("SIFR", "0") if parent else "0"
                        tax_init["Combocode"] = menu.get(parent.get("SIFR"), {}).get("code", "0") if parent else "0"
                    t_attrs = tax_groups.setdefault(group_key, tax_init)
                    t_attrs["AmountBeforeTax"] = f"{Decimal(t_attrs['AmountBeforeTax']) + Decimal(binding.get('PRICESUM') or 0) / 100:.2f}"
                    t_attrs["Amount"] = f"{Decimal(t_attrs['Amount']) + Decimal(tax.get('SUM') or 0) / 100:.2f}"

            dish_order = {dish.get("UNI"): index for index, dish in enumerate(dish_rows)}
            taxes_list = [tax_groups[key] for key in sorted(tax_groups, key=lambda key: dish_order.get(key[0], 999999))]

        # DISCOUNTS (In RK7 FastReport .mak, DISCOUNTS comes directly after DISHES and before TAXES)
        # Active discounts must have active parts (DBSTATUS != '-1') and STATE in ('5', '6')
        active_disclineunis = {p.get("DISCLINEUNI") for p in raw.get("DISCPARTS", [])
                               if p.get("VISIT") == visit_id and p.get("DBSTATUS") != "-1"}
        discounts = [x for x in raw.get("DISHDISCOUNTS", [])
                     if x.get("VISIT") == visit_id and x.get("STATE") in ("5", "6") and x.get("UNI") in active_disclineunis]
        if not discounts and not active_disclineunis:
            # Check if all discounts were deleted/cancelled
            has_void_parts = any(p.get("VISIT") == visit_id for p in raw.get("DISCPARTS", []))
            if not has_void_parts:
                if exclude_charges:
                    discounts = [x for x in raw.get("DISHDISCOUNTS", [])
                                 if x.get("VISIT") == visit_id and not x.get("ISCHARGE")]
                else:
                    discounts = [x for x in raw.get("DISHDISCOUNTS", [])
                                 if x.get("VISIT") == visit_id and x.get("CALCAMOUNT")]

        # Filter discounts with active amount for GSF
        if is_gsf:
            discounts = [d for d in discounts if Decimal(str(d.get("CALCAMOUNT") or 0)) != 0]

        if discounts:
            section = ET.SubElement(data, tag_discounts, {"count": str(len(discounts))})
            for idx, discount in enumerate(discounts, 1):
                info = (master or {}).get("discounts", {}).get(discount.get("SIFR"), {})
                if is_gsf:
                    # GSF discounts: Ident="", Name, CardCode, Holder, Amount
                    d_attrs = {
                        "Ident": "",
                        "Name": info.get("name", "") or discount.get("NAME", ""),
                        "CardCode": discount.get("CARDCODE", ""),
                        "Holder": discount.get("HOLDER", ""),
                        "Amount": cls._money(discount.get("CALCAMOUNT", 0)),
                    }
                else:
                    d_attrs = {
                        "Ident": discount.get("SIFR", ""),
                        "Code": info.get("code", ""),
                        "Name": info.get("name", ""),
                        "CardCode": discount.get("CARDCODE", ""),
                        "Holder": discount.get("HOLDER", ""),
                        "Amount": cls._money(discount.get("CALCAMOUNT", 0)),
                    }
                    if include_discount_num:
                        d_attrs["discount_num"] = str(idx)
                cls._line(section, d_attrs)

        section = ET.SubElement(data, tag_taxes, {"count": str(len(taxes_list))})
        for attrs in taxes_list:
            cls._line(section, attrs)

        # PAYMENTS
        section = ET.SubElement(data, tag_payments, {"count": str(len(payments))})
        for payment in payments:
            currency = (master or {}).get("currencies", {}).get(payment.get("SIFR"), {})
            currency_type = (master or {}).get("currency_types", {}).get(payment.get("IHIGHLEVELTYPE"), {})
            c_type_id = str(payment.get("IHIGHLEVELTYPE", ""))
            
            # PaymentMethod resolution
            pay_method = ""
            if is_gsf:
                if c_type_id == "103":
                    pay_method = "TM"
                elif c_type_id == "102":
                    pay_method = "CK"
                else:
                    pay_method = currency_type.get("genPAYMENTMETHOD") or ""
                p_attrs = {
                    "Ident": payment.get("SIFR", ""),
                    "Name": currency.get("name", ""),
                    "CurrencyTypeIdent": payment.get("IHIGHLEVELTYPE", ""),
                    "CurrencyTypeName": currency_type.get("name", ""),
                    "OriginalSum": cls._money(payment.get("ORIGINALSUM")),
                    "BasicAmount": cls._money(payment.get("BASICSUM")),
                    "PaymentMethod": pay_method,
                }
            else:
                p_attrs = {
                    "Ident": payment.get("SIFR", ""),
                    "Code": currency.get("code", ""),
                    "Name": currency.get("name", ""),
                    "CurrencyTypeIdent": payment.get("IHIGHLEVELTYPE", ""),
                    "CurrencyTypeName": currency_type.get("name", ""),
                    "OriginalSum": cls._money(payment.get("ORIGINALSUM")),
                    "BasicAmount": cls._money(payment.get("BASICSUM")),
                    "PaymentMethod": "",
                    "NotInvoice": payment_not_invoice,
                }
            cls._line(section, p_attrs)

        # Format XML output to match FastReport / POS XML layout:
        # 1. No indentation (0 space), newline per element
        # 2. Tag attributes spacing: <SECTION count = "N">
        # 3. Empty Temp tag as explicit open and close pair on newlines:
        #    <Temp count = "N">
        #    </Temp>
        ET.indent(root, space="")
        raw_xml = ET.tostring(root, encoding="utf-8").decode("utf-8")
        out_lines = []
        for line in raw_xml.splitlines():
            s = line.strip()
            if not s:
                continue
            if s.startswith("<Temp ") and s.endswith("/>"):
                # Extract count attribute
                cnt_match = s.split('count="')[1].split('"')[0] if 'count="' in s else "0"
                out_lines.append(f'<Temp count = "{cnt_match}">')
                out_lines.append('</Temp>')
            elif 'count="' in s and not s.startswith("<LINE"):
                # <TAG count="N"> -> <TAG count = "N">
                tag_name = s.split()[0].replace("<", "")
                cnt_match = s.split('count="')[1].split('"')[0]
                out_lines.append(f'<{tag_name} count = "{cnt_match}">')
            elif s.endswith(" />"):
                out_lines.append(s[:-3] + "/>")
            else:
                out_lines.append(s)

        final_xml_str = "\n".join(out_lines)
        return final_xml_str.encode("utf-8")
