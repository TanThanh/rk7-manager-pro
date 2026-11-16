"""Service for connecting directly to RK7 SQL Server to test connections and sync master data."""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import time
from typing import Any, Callable, Dict, List, Optional

import sys

logger = logging.getLogger("rk7_pro.sql_master_sync")

def _get_base_data_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def decode_cp1258(value: Any) -> str:
    """Safely decode CP1258/Vietnamese string."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        for enc in ("cp1258", "utf-8", "windows-1252"):
            try:
                return value.decode(enc).strip()
            except UnicodeDecodeError:
                continue
        return value.decode("cp1258", errors="ignore").strip()
    return str(value).strip()


class SqlMasterSyncService:
    @classmethod
    def get_config_file(cls) -> Path:
        base = _get_base_data_dir()
        file = base / "sql_connections.json"
        if file.is_file():
            return file
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            meipass_file = Path(sys._MEIPASS) / "sql_connections.json"
            if meipass_file.is_file():
                return meipass_file
        source_file = Path(__file__).resolve().parents[2] / "sql_connections.json"
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
        """Load list of SQL connection profiles."""
        config_file = cls.get_config_file()
        if not config_file.is_file():
            return []
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load sql_connections.json: %s", e)
            return []

    @classmethod
    def save_connections(cls, connections: List[Dict[str, Any]]) -> bool:
        """Save SQL connection profiles to json."""
        try:
            config_file = cls.get_config_file()
            config_file.write_text(
                json.dumps(connections, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            return True
        except Exception as e:
            logger.error("Failed to save sql_connections.json: %s", e)
            return False

    @staticmethod
    def _build_connection_string(profile: Dict[str, Any]) -> str:
        """Build ADODB / OLEDB / ODBC connection string for SQL Server."""
        host = profile.get("host", "").strip()
        db = profile.get("database", "").strip()
        user = profile.get("user", "").strip()
        password = profile.get("password", "").strip()

        # Try MSOLEDBSQL or SQLOLEDB
        if user:
            return f"Provider=SQLOLEDB;Data Source={host};Initial Catalog={db};User ID={user};Password={password};"
        else:
            return f"Provider=SQLOLEDB;Data Source={host};Initial Catalog={db};Integrated Security=SSPI;"

    @classmethod
    def test_connection(cls, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Test read-only SQL connection."""
        try:
            import win32com.client
            conn = win32com.client.Dispatch("ADODB.Connection")
            conn.ConnectionTimeout = 8
            conn.CommandTimeout = 8
            conn_str = cls._build_connection_string(profile)
            conn.Open(conn_str)

            # Test simple non-locking query
            rs = win32com.client.Dispatch("ADODB.Recordset")
            rs.Open("SELECT @@VERSION AS ver, DB_NAME() AS dbname", conn, 0, 1) # 0=adOpenForwardOnly, 1=adLockReadOnly
            version = str(rs.Fields("ver").Value) if not rs.EOF else ""
            dbname = str(rs.Fields("dbname").Value) if not rs.EOF else ""
            rs.Close()
            conn.Close()

            return {
                "success": True,
                "message": f"Kết nối thành công tới database '{dbname}'!",
                "server_version": version.split("\n")[0] if version else ""
            }
        except Exception as e:
            err_msg = str(e)
            return {
                "success": False,
                "error": f"Lỗi kết nối: {err_msg}"
            }

    @classmethod
    def sync_master_data(cls, profile_id: str, progress_callback: Optional[Callable] = None) -> Dict[str, Any]:
        """Fetch all 11 master tables from SQL Server using WITH (NOLOCK) and save to master_refs with live progress."""
        connections = cls.load_connections()
        profile = next((p for p in connections if p.get("id") == profile_id), None)
        if not profile:
            return {"success": False, "error": f"Không tìm thấy cấu hình kết nối #{profile_id}"}

        package_id = re.sub(r"[^a-zA-Z0-9_]", "_", profile.get("package_id") or profile.get("id") or "master").lower().strip("_")

        start_time = time.time()
        def notify(step, total, table, status, message, count=None):
            if progress_callback:
                try:
                    progress_callback(step, total, table, status, message, count)
                except Exception as ex:
                    logger.warning("Progress callback error: %s", ex)

        try:
            import win32com.client
            notify(0, 12, "CONNECT", "running", f"Đang kết nối tới SQL Server ({profile.get('host')})...")
            conn = win32com.client.Dispatch("ADODB.Connection")
            conn.ConnectionTimeout = 15
            conn.CommandTimeout = 60
            conn_str = cls._build_connection_string(profile)
            conn.Open(conn_str)
            notify(0, 12, "CONNECT", "done", "Kết nối SQL Server thành công!")

            def query_table(sql: str, field_names: List[str]) -> List[Dict[str, Any]]:
                rs = win32com.client.Dispatch("ADODB.Recordset")
                rows = []
                try:
                    rs.Open(sql, conn, 0, 1) # adOpenForwardOnly, adLockReadOnly
                    while not rs.EOF:
                        row = {}
                        for fname in field_names:
                            try:
                                val = rs.Fields(fname).Value
                                row[fname] = decode_cp1258(val) if isinstance(val, (str, bytes)) else val
                            except Exception:
                                row[fname] = None
                        rows.append(row)
                        rs.MoveNext()
                except Exception as q_err:
                    logger.warning("Query failed (%s): %s", sql, q_err)
                finally:
                    try:
                        rs.Close()
                    except Exception:
                        pass
                return rows

            # 1. RESTAURANTS
            notify(1, 12, "RESTAURANTS", "running", "Đang truy vấn bảng RESTAURANTS WITH (NOLOCK)...")
            restaurants = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME, GUIDSTRING, CONCEPT FROM RESTAURANTS WITH (NOLOCK) WHERE STATUS = 3 OR STATUS = 0 OR STATUS IS NULL",
                ["SIFR", "CODE", "NAME", "GUIDSTRING", "CONCEPT"]
            ):
                sifr = str(r["SIFR"])
                restaurants[sifr] = {
                    "code": r["CODE"],
                    "name": r["NAME"],
                    "guid": r["GUIDSTRING"] or "",
                    "concept": str(r["CONCEPT"]) if r["CONCEPT"] is not None else ""
                }
            notify(1, 12, "RESTAURANTS", "done", f"Tải xong {len(restaurants)} nhà hàng", len(restaurants))

            # 2. PRICETYPES
            notify(2, 12, "PRICETYPES", "running", "Đang truy vấn bảng PRICETYPES WITH (NOLOCK)...")
            price_scales = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME, GUIDSTRING FROM PRICETYPES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME", "GUIDSTRING"]
            ):
                price_scales[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"],
                    "guid": r["GUIDSTRING"] or ""
                }
            notify(2, 12, "PRICETYPES", "done", f"Tải xong {len(price_scales)} bậc giá", len(price_scales))

            # 3. EMPLOYEES
            notify(3, 12, "EMPLOYEES", "running", "Đang truy vấn bảng EMPLOYEES WITH (NOLOCK)...")
            employees = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM EMPLOYEES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                employees[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }
            notify(3, 12, "EMPLOYEES", "done", f"Tải xong {len(employees)} nhân viên", len(employees))

            # 4. CURRENCIES & CURRENCYTYPES
            notify(4, 12, "CURRENCIES", "running", "Đang truy vấn CURRENCIES & CURRENCYTYPES...")
            currencies = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM CURRENCIES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                currencies[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }

            currency_types = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM CURRENCYTYPES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                currency_types[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }
            notify(4, 12, "CURRENCIES", "done", f"Tải xong {len(currencies)} loại tiền tệ", len(currencies))

            # 5. DISCOUNTS
            notify(5, 12, "DISCOUNTS", "running", "Đang truy vấn bảng DISCOUNTS...")
            discounts = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM DISCOUNTS WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                discounts[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }
            notify(5, 12, "DISCOUNTS", "done", f"Tải xong {len(discounts)} chiết khấu", len(discounts))

            # 6. TRADEGROUPS
            notify(6, 12, "TRADEGROUPS", "running", "Đang truy vấn bảng TRADEGROUPS...")
            trade_groups = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME, PRICETYPE FROM TRADEGROUPS WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME", "PRICETYPE"]
            ):
                trade_groups[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"],
                    "price_type": str(r["PRICETYPE"]) if r["PRICETYPE"] else None
                }
            notify(6, 12, "TRADEGROUPS", "done", f"Tải xong {len(trade_groups)} nhóm bán hàng", len(trade_groups))

            # 7. ORDER TYPES
            notify(7, 12, "ORDERTYPES", "running", "Đang truy vấn bảng UNCHANGEABLEORDERTYPES...")
            order_types = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM UNCHANGEABLEORDERTYPES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                order_types[str(r["SIFR"])] = {"code": r["CODE"], "name": r["NAME"]}
            notify(7, 12, "ORDERTYPES", "done", f"Tải xong {len(order_types)} loại đơn hàng", len(order_types))

            # 8. CATEGLIST
            notify(8, 12, "CATEGLIST", "running", "Đang truy vấn cây nhóm thực đơn CATEGLIST...")
            categories = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME, PARENT FROM CATEGLIST WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME", "PARENT"]
            ):
                categories[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"],
                    "parent": str(r["PARENT"]) if r["PARENT"] else None
                }
            notify(8, 12, "CATEGLIST", "done", f"Tải xong {len(categories)} nhóm thực đơn", len(categories))

            # 9. TABLES
            notify(9, 12, "TABLES", "running", "Đang truy vấn danh mục bàn TABLES...")
            tables = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM TABLES WITH (NOLOCK)",
                ["SIFR", "CODE", "NAME"]
            ):
                tables[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }
            notify(9, 12, "TABLES", "done", f"Tải xong {len(tables)} bàn", len(tables))

            # 10. MODIFIERS
            notify(10, 12, "MODIFIERS", "running", "Đang truy vấn topping & món phụ MODIFIERS...")
            modifiers = {}
            for r in query_table(
                "SELECT SIFR, CODE, NAME FROM MODIFIERS WITH (NOLOCK) WHERE STATUS = 3 OR STATUS = 0 OR STATUS IS NULL",
                ["SIFR", "CODE", "NAME"]
            ):
                modifiers[str(r["SIFR"])] = {
                    "code": r["CODE"],
                    "name": r["NAME"]
                }
            notify(10, 12, "MODIFIERS", "done", f"Tải xong {len(modifiers)} món phụ/modifier", len(modifiers))

            # 11. PROPERTIES (Mã SAP, MONTV, NOTINVOICE trong GENERATEDPROPDATAS)
            notify(11, 12, "PROPERTIES", "running", "Đang bóc tách mã SAP, MONTV trong GENERATEDPROPDATAS...")
            props_by_dish = {}
            prop_names = {}

            # 11.1. Discover property names from GENERATEDPROPTYPES if available
            try:
                for p_def in query_table(
                    "SELECT SIFR, NAME, RKPROPNAME FROM GENERATEDPROPTYPES WITH (NOLOCK)",
                    ["SIFR", "NAME", "RKPROPNAME"]
                ):
                    p_sifr = str(p_def["SIFR"])
                    p_name = (p_def["NAME"] or p_def["RKPROPNAME"] or "").strip()
                    if p_name:
                        prop_names[p_sifr] = p_name
            except Exception as ex:
                logger.debug("Could not read GENERATEDPROPTYPES: %s", ex)

            # 11.2. Discover all tables matching GENERATEDPROPDATAS%
            candidate_prop_tables = []
            try:
                found_tbls = query_table(
                    "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WITH (NOLOCK) WHERE TABLE_NAME LIKE 'GENERATEDPROPDATAS%'",
                    ["TABLE_NAME"]
                )
                for ft in found_tbls:
                    tname = ft.get("TABLE_NAME")
                    if tname:
                        if "MENUITEMS" in tname.upper():
                            candidate_prop_tables.insert(0, tname)
                        else:
                            candidate_prop_tables.append(tname)
            except Exception as tbl_ex:
                logger.debug("Could not query INFORMATION_SCHEMA: %s", tbl_ex)

            if not candidate_prop_tables:
                candidate_prop_tables = ["GENERATEDPROPDATAS_MENUITEMS_1000008", "GENERATEDPROPDATAS"]

            for prop_tbl in candidate_prop_tables:
                try:
                    for s_row in query_table(
                        f"SELECT OBJECTIDENT, OBJECTREFNO, PROPERTYVAL FROM [{prop_tbl}] WITH (NOLOCK) WHERE PROPERTYVAL IS NOT NULL AND PROPERTYVAL <> ''",
                        ["OBJECTIDENT", "OBJECTREFNO", "PROPERTYVAL"]
                    ):
                        ident_str = str(s_row["OBJECTIDENT"])
                        refno_str = str(s_row["OBJECTREFNO"])
                        val = str(s_row["PROPERTYVAL"]).strip()
                        if ident_str not in props_by_dish:
                            props_by_dish[ident_str] = {}
                        if refno_str not in props_by_dish[ident_str]:
                            props_by_dish[ident_str][refno_str] = val
                except Exception as ex:
                    logger.debug("Table %s not accessible for properties: %s", prop_tbl, ex)

            notify(11, 12, "PROPERTIES", "done", f"Bóc tách xong {len(props_by_dish)} thuộc tính mở rộng", len(props_by_dish))

            # Helper queries: PRICES, MODIFIERSCHEMES, TAXDISHGROUPS
            prices_by_dish = {}
            for pr in query_table("SELECT OBJECTID, PRICESCALE, VALUE FROM PRICES WITH (NOLOCK)", ["OBJECTID", "PRICESCALE", "VALUE"]):
                d_id = str(pr["OBJECTID"])
                if d_id not in prices_by_dish:
                    prices_by_dish[d_id] = []
                ps_id = str(pr["PRICESCALE"]) if pr["PRICESCALE"] is not None else ""
                ps_name = price_scales.get(ps_id, {}).get("name") if ps_id in price_scales else (f"Bậc {ps_id}" if ps_id else "Mặc định")
                val = pr["VALUE"]
                try:
                    val_num = float(val) if val is not None else 0
                except Exception:
                    val_num = val
                prices_by_dish[d_id].append({
                    "scale_id": ps_id,
                    "scale_name": ps_name,
                    "price": val_num
                })

            modi_schemes = {}
            for ms in query_table("SELECT SIFR, NAME FROM MODIFIERSCHEMES WITH (NOLOCK)", ["SIFR", "NAME"]):
                modi_schemes[str(ms["SIFR"])] = ms["NAME"]

            tax_dish_groups = {}
            for tg in query_table("SELECT SIFR, NAME FROM TAXDISHGROUPS WITH (NOLOCK)", ["SIFR", "NAME"]):
                tax_dish_groups[str(tg["SIFR"])] = tg["NAME"]

            # 12. MENUITEMS
            notify(12, 12, "MENUITEMS", "running", "Đang truy vấn danh mục món ăn MENUITEMS...")
            menu_items = {}
            
            # Attempt extended columns query first
            menu_rows = query_table(
                "SELECT SIFR, CODE, NAME, ALTNAME, STATUS, TOPARENTCATEG, PORTIONNAME, EXTCODE, TAXDISHGROUP, MODISCHEME, STARTSALE, ENDSALE, TRADEGROUP FROM MENUITEMS WITH (NOLOCK) WHERE STATUS = 3 OR STATUS = 0 OR STATUS IS NULL",
                ["SIFR", "CODE", "NAME", "ALTNAME", "STATUS", "TOPARENTCATEG", "PORTIONNAME", "EXTCODE", "TAXDISHGROUP", "MODISCHEME", "STARTSALE", "ENDSALE", "TRADEGROUP"]
            )
            if not menu_rows:
                # Fallback to safe basic query
                menu_rows = query_table(
                    "SELECT SIFR, CODE, NAME, TOPARENTCATEG, PORTIONNAME, EXTCODE FROM MENUITEMS WITH (NOLOCK) WHERE STATUS = 3 OR STATUS = 0 OR STATUS IS NULL",
                    ["SIFR", "CODE", "NAME", "TOPARENTCATEG", "PORTIONNAME", "EXTCODE"]
                )

            for r in menu_rows:
                sifr_str = str(r["SIFR"])
                raw_unit = (r.get("PORTIONNAME") or "").strip()
                normalized_unit = raw_unit
                if raw_unit == "Phần":
                    normalized_unit = "POR"
                elif raw_unit == "Lon":
                    normalized_unit = "BOT"

                dish_props = props_by_dish.get(sifr_str, {})
                sapcode_val = dish_props.get("10", "")
                if not sapcode_val:
                    for r_key, r_val in dish_props.items():
                        if "SAP" in prop_names.get(r_key, "").upper():
                            sapcode_val = r_val
                            break
                if not sapcode_val:
                    sapcode_val = str(r.get("EXTCODE") or "")

                montv_name = dish_props.get("1000025", "")
                not_invoice_flag = (dish_props.get("1000046") == "1")

                m_scheme_id = str(r.get("MODISCHEME") or "")
                m_scheme_name = modi_schemes.get(m_scheme_id, "")
                t_group_id = str(r.get("TRADEGROUP") or "")
                t_group_name = trade_groups.get(t_group_id, {}).get("name", "") if t_group_id in trade_groups else ""
                t_dish_id = str(r.get("TAXDISHGROUP") or "")
                t_dish_name = tax_dish_groups.get(t_dish_id, "")

                status_raw = str(r.get("STATUS") if r.get("STATUS") is not None else "3")
                status_label = "Active" if status_raw == "3" else ("Suspended" if status_raw in ("1", "2") else "Deleted" if status_raw == "0" else f"Status {status_raw}")

                start_date_val = str(r.get("STARTSALE") or "")
                end_date_val = str(r.get("ENDSALE") or "")

                menu_items[sifr_str] = {
                    "code": r["CODE"],
                    "name": r["NAME"],
                    "altname": r.get("ALTNAME") or "",
                    "status": status_label,
                    "status_code": status_raw,
                    "montv": montv_name,
                    "not_invoice": not_invoice_flag,
                    "categ": r.get("TOPARENTCATEG"),
                    "unit": normalized_unit,
                    "sapcode": sapcode_val,
                    "props": dish_props,
                    "external_code": str(r.get("EXTCODE") or ""),
                    "tax_group_id": t_dish_id,
                    "tax_group_name": t_dish_name,
                    "modi_scheme_id": m_scheme_id,
                    "modi_scheme_name": m_scheme_name,
                    "trade_group_id": t_group_id,
                    "trade_group_name": t_group_name,
                    "start_date": start_date_val,
                    "end_date": end_date_val,
                    "prices": prices_by_dish.get(sifr_str, [])
                }
            notify(12, 12, "MENUITEMS", "done", f"Tải xong {len(menu_items)} món ăn", len(menu_items))

            conn.Close()

            # Compile into standard master JSON
            master_data = {
                "package_id": package_id,
                "display_name": profile.get("name") or package_id,
                "exported_at": datetime.now().isoformat(),
                "source": f"SQL Server ({profile.get('host')}/{profile.get('database')})",
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
                "categories": categories
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
                "source_file": f"SQL: {profile.get('host')}/{profile.get('database')}",
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
            profile["last_synced"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            profile["stats"] = {
                "restaurants_count": len(restaurants),
                "menu_items_count": len(menu_items),
                "employees_count": len(employees),
                "tables_count": len(tables),
                "duration_sec": duration
            }
            cls.save_connections(connections)

            notify(12, 12, "FINISHED", "done", f"Đồng bộ SQL hoàn tất trong {duration}s! ({len(restaurants)} quán, {len(menu_items)} món)", len(menu_items))

            return {
                "success": True,
                "message": f"Đồng bộ thành công Master Data '{package_id}'!",
                "stats": profile["stats"],
                "last_synced": profile["last_synced"]
            }

        except Exception as e:
            logger.error("SQL Sync failed: %s", e)
            notify(12, 12, "ERROR", "error", f"Lỗi đồng bộ SQL: {str(e)}", 0)
            return {"success": False, "error": f"Lỗi đồng bộ SQL: {str(e)}"}
