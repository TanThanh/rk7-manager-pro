"""
Module quản lý và bóc tách Master Data từ các file refsdata.udb (SQLite format 3)
của R-Keeper 7 sang định dạng JSON tinh gọn phục vụ CheckView và mở rộng.
"""

import os
import re
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, List


def decode_cp1258(val: Any) -> str:
    """Decode chuỗi byte từ SQLite RK7 sang UTF-8 tiếng Việt chuẩn (CP1258/CP1252 fallback)."""
    if val is None:
        return ""
    if isinstance(val, bytes):
        try:
            return val.decode("cp1258")
        except Exception:
            try:
                return val.decode("utf-8")
            except Exception:
                return val.decode("latin1", errors="ignore")
    return str(val)


class RefMasterService:
    def __init__(self, storage_dir: Optional[Path] = None):
        import sys
        if storage_dir is None:
            if getattr(sys, "frozen", False):
                storage_dir = Path(sys.executable).resolve().parent / "master_refs"
                if (not Path(storage_dir).is_dir() or not any(Path(storage_dir).iterdir())) and hasattr(sys, "_MEIPASS"):
                    meipass_refs = Path(sys._MEIPASS) / "master_refs"
                    if meipass_refs.is_dir():
                        storage_dir = meipass_refs
            else:
                storage_dir = Path(__file__).resolve().parent.parent.parent / "master_refs"
            if not Path(storage_dir).is_dir():
                source_dir = Path(__file__).resolve().parent.parent.parent / "master_refs"
                if source_dir.is_dir():
                    storage_dir = source_dir
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.storage_dir / "index_map.json"
        self._index_map = self._load_index()

    def _load_index(self) -> Dict[str, Any]:
        """Tải bản đồ ánh xạ nhanh: Restaurant_ID -> Tên file Master JSON."""
        if self.index_file.is_file():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"restaurants": {}, "packages": {}}

    def _save_index(self):
        """Lưu lại bản đồ ánh xạ index_map.json."""
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self._index_map, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[RefMasterService] Lỗi lưu index: {e}")

    def is_sqlite_udb(self, file_path: Path) -> bool:
        """Kiểm tra tệp có đúng định dạng SQLite (refsdata.udb chuẩn của RK7) hay không."""
        try:
            with open(file_path, "rb") as f:
                header = f.read(16)
            return header.startswith(b"SQLite format 3")
        except Exception:
            return False

    def extract_refsdata_to_json(
        self,
        udb_path: Path,
        package_id: Optional[str] = None,
        display_name: Optional[str] = None,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Bóc tách toàn diện các bảng kinh doanh từ refsdata.udb sang cấu trúc JSON tinh gọn.
        Đồng thời tự động lấy danh sách nhà hàng để lập chỉ mục nhận diện.
        Nếu overwrite=True hoặc package_id được chỉ định rõ, cho phép cập nhật đè gói Master Data hiện có.
        """
        udb_path = Path(udb_path).resolve()
        if not udb_path.is_file():
            raise FileNotFoundError(f"Không tìm thấy file: {udb_path}")

        if not self.is_sqlite_udb(udb_path):
            raise ValueError(f"Tệp {udb_path.name} không phải định dạng SQLite Master Data của RK7.")

        conn = sqlite3.connect(str(udb_path))
        c = conn.cursor()

        # Kiểm tra danh sách bảng hiện có
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        existing_tables = set(r[0] for r in c.fetchall())

        # 1. Trích xuất RESTAURANTS (Nhận diện chuỗi / cơ sở)
        restaurants = {}
        if "RESTAURANTS" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME, GUIDSTRING, CONCEPT FROM RESTAURANTS WHERE STATUS IN (0, 1, 2, 3) OR STATUS IS NULL")
            for r in c.fetchall():
                restaurants[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2]),
                    "guid": decode_cp1258(r[3]),
                    "concept": str(r[4]) if r[4] is not None else ""
                }

        # Xử lý package_id và display_name
        if package_id:
            package_id = re.sub(r"[^a-zA-Z0-9_]", "_", str(package_id)).lower().strip("_")
        
        if not package_id:
            base_name = udb_path.stem.replace("refsdata_", "").replace("refsdata", "master")
            clean_name = re.sub(r"[^a-zA-Z0-9_]", "_", base_name).lower()
            package_id = clean_name or "master_default"

        if not overwrite:
            base_id = package_id
            suffix = 2
            while package_id in self._index_map.get("packages", {}) or (self.storage_dir / f"{package_id}.json").exists():
                package_id = f"{base_id}_{suffix}"
                suffix += 1

        final_display_name = display_name or self._index_map.get("packages", {}).get(package_id, {}).get("display_name") or package_id

        # 2. Trích xuất PRICETYPES (Thang đơn giá - IPRICESCALE)
        price_scales = {}
        if "PRICETYPES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME, GUIDSTRING FROM PRICETYPES")
            for r in c.fetchall():
                price_scales[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2]),
                    "guid": decode_cp1258(r[3])
                }

        # 3. Trích xuất EMPLOYEES (Nhân viên / Thu ngân)
        employees = {}
        if "EMPLOYEES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM EMPLOYEES")
            for r in c.fetchall():
                employees[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        # 4. Trích xuất CURRENCIES (Hình thức thanh toán)
        currencies = {}
        if "CURRENCIES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM CURRENCIES")
            for r in c.fetchall():
                currencies[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        # 5. Trích xuất DISCOUNTS (Khuyến mãi / Giảm giá)
        discounts = {}
        if "DISCOUNTS" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM DISCOUNTS")
            for r in c.fetchall():
                discounts[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        # 6. Trích xuất TRADEGROUPS (Nhóm bán hàng)
        trade_groups = {}
        if "TRADEGROUPS" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME, PRICETYPE FROM TRADEGROUPS")
            for r in c.fetchall():
                trade_groups[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2]),
                    "price_type": str(r[3]) if r[3] else None
                }

        # 7. Trích xuất MENUITEMS (Món ăn)
        menu_items = {}
        if "MENUITEMS" in existing_tables:
            # Query custom properties (OBJECTREFNO) for Menu Items dynamically from GENERATEDPROPDATAS%
            props_by_dish = {}
            prop_names = {}

            if "GENERATEDPROPTYPES" in existing_tables:
                try:
                    c.execute("SELECT SIFR, NAME, RKPROPNAME FROM GENERATEDPROPTYPES")
                    for p_row in c.fetchall():
                        p_sifr = str(p_row[0])
                        p_name = (decode_cp1258(p_row[1]) or decode_cp1258(p_row[2]) or "").strip()
                        if p_name:
                            prop_names[p_sifr] = p_name
                except Exception:
                    pass

            prop_tables = [t for t in existing_tables if t.startswith("GENERATEDPROPDATAS")]
            # Ưu tiên các bảng dành riêng cho menuitems trước
            prop_tables.sort(key=lambda x: (0 if "MENUITEMS" in x.upper() else 1, x))

            for pt in prop_tables:
                try:
                    c.execute(f"PRAGMA table_info([{pt}])")
                    col_names = [r[1] for r in c.fetchall()]
                    has_rktype = "RKTYPEIDENT" in col_names
                    has_refno = "OBJECTREFNO" in col_names

                    if has_rktype and has_refno:
                        c.execute(f"SELECT OBJECTIDENT, RKTYPEIDENT, PROPERTYVAL FROM [{pt}] WHERE (OBJECTREFNO = 10 OR OBJECTREFNO IS NULL) AND PROPERTYVAL IS NOT NULL AND PROPERTYVAL <> ''")
                    elif has_rktype:
                        c.execute(f"SELECT OBJECTIDENT, RKTYPEIDENT, PROPERTYVAL FROM [{pt}] WHERE PROPERTYVAL IS NOT NULL AND PROPERTYVAL <> ''")
                    else:
                        c.execute(f"SELECT OBJECTIDENT, OBJECTREFNO, PROPERTYVAL FROM [{pt}] WHERE PROPERTYVAL IS NOT NULL AND PROPERTYVAL <> ''")

                    for s_row in c.fetchall():
                        ident_str = str(s_row[0])
                        prop_type_id = str(s_row[1])
                        val = decode_cp1258(s_row[2])
                        if ident_str not in props_by_dish:
                            props_by_dish[ident_str] = {}
                        props_by_dish[ident_str][prop_type_id] = val
                except Exception:
                    pass

            c.execute("SELECT SIFR, CODE, NAME, TOPARENTCATEG, PORTIONNAME, EXTCODE FROM MENUITEMS")
            for r in c.fetchall():
                sifr_str = str(r[0])
                raw_u = decode_cp1258(r[4])
                # Chuẩn hóa đơn vị tính
                unit_norm = raw_u
                if raw_u == "Phần":
                    unit_norm = "POR"
                elif raw_u == "Lon":
                    unit_norm = "BOT"

                dish_props = props_by_dish.get(sifr_str, {})
                # Resolve sapcode tự động
                sapcode_val = dish_props.get("10", "")
                if not sapcode_val:
                    for r_key, r_val in dish_props.items():
                        if "SAP" in prop_names.get(r_key, "").upper():
                            sapcode_val = r_val
                            break

                # Đọc MONTV (1000025) và NOTINVOICE (1000046) nếu có
                montv_name = dish_props.get("1000025", "")
                not_invoice_flag = (dish_props.get("1000046") == "1")

                menu_items[sifr_str] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2]),
                    "montv": montv_name,
                    "not_invoice": not_invoice_flag,
                    "categ": r[3],
                    "unit": unit_norm,
                    "sapcode": sapcode_val,
                    "props": dish_props,
                    "external_code": str(r[5]) if r[5] is not None else ""
                }

        order_types = {}
        if "UNCHANGEABLEORDERTYPES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM UNCHANGEABLEORDERTYPES")
            for r in c.fetchall():
                order_types[str(r[0])] = {"code": r[1], "name": decode_cp1258(r[2])}

        currency_types = {}
        if "CURRENCYTYPES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM CURRENCYTYPES")
            for r in c.fetchall():
                currency_types[str(r[0])] = {"code": r[1], "name": decode_cp1258(r[2])}

        # 8. Trích xuất MODIFIERS (Topping / Yêu cầu bếp)
        modifiers = {}
        if "MODIFIERS" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM MODIFIERS")
            for r in c.fetchall():
                modifiers[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        # 9. Trích xuất TABLES (Danh mục bàn)
        tables = {}
        if "TABLES" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM TABLES")
            for r in c.fetchall():
                tables[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        # 10. Trích xuất CATEGLIST (Nhóm thực đơn)
        categories = {}
        if "CATEGLIST" in existing_tables:
            c.execute("SELECT SIFR, CODE, NAME FROM CATEGLIST")
            for r in c.fetchall():
                categories[str(r[0])] = {
                    "code": r[1],
                    "name": decode_cp1258(r[2])
                }

        conn.close()

        master_package = {
            "package_id": package_id,
            "display_name": final_display_name,
            "source_file": udb_path.name,
            "total_restaurants": len(restaurants),
            "total_menu_items": len(menu_items),
            "total_price_scales": len(price_scales),
            "total_employees": len(employees),
            "restaurants": restaurants,
            "price_scales": price_scales,
            "employees": employees,
            "currencies": currencies,
            "discounts": discounts,
            "trade_groups": trade_groups,
            "menu_items": menu_items,
            "order_types": order_types,
            "currency_types": currency_types,
            "modifiers": modifiers,
            "tables": tables,
            "categories": categories
        }

        # Lưu file JSON
        out_json_path = self.storage_dir / f"{package_id}.json"
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(master_package, f, ensure_ascii=False, indent=2)

        # Cập nhật Index Map
        for rest_id, rest_info in restaurants.items():
            self._index_map["restaurants"][str(rest_id)] = {
                "package_id": package_id,
                "name": rest_info["name"]
            }

        file_size_kb = out_json_path.stat().st_size / 1024
        self._index_map["packages"][package_id] = {
            "file": f"{package_id}.json",
            "display_name": final_display_name,
            "source_file": udb_path.name,
            "restaurants_count": len(restaurants),
            "menu_items_count": len(menu_items),
            "price_scales_count": len(price_scales),
            "size_kb": round(file_size_kb, 1)
        }
        self._save_index()

        return {
            "success": True,
            "package_id": package_id,
            "display_name": final_display_name,
            "json_path": str(out_json_path),
            "size_kb": round(file_size_kb, 1),
            "restaurants_count": len(restaurants),
            "price_scales_count": len(price_scales),
            "menu_items_count": len(menu_items)
        }

    def get_master_data_for_restaurant(self, restaurant_id: Any) -> Optional[Dict[str, Any]]:
        """Lấy dữ liệu Master Data tương ứng cho một mã nhà hàng (IRESTAURANT)."""
        self._index_map = self._load_index()
        rest_key = str(restaurant_id).strip()
        pkg_info = self._index_map.get("restaurants", {}).get(rest_key)
        if not pkg_info:
            return None

        pkg_id = pkg_info["package_id"]
        json_file = self.storage_dir / f"{pkg_id}.json"
        if not json_file.is_file():
            return None

        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["display_name"] = self._index_map.get("packages", {}).get(pkg_id, {}).get("display_name") or pkg_id
            return data
        except Exception:
            return None

    def list_packages(self) -> List[Dict[str, Any]]:
        """Liệt kê các gói Master Data đã được nạp."""
        self._index_map = self._load_index()
        return [
            {"package_id": k, "display_name": v.get("display_name") or k, **v}
            for k, v in self._index_map.get("packages", {}).items()
        ]

    def rename_package(self, package_id: str, display_name: str, new_package_id: Optional[str] = None) -> Dict[str, Any]:
        """Rename the visible label and optionally update package_id."""
        package_id = str(package_id)
        name = " ".join(str(display_name).split())
        self._index_map = self._load_index()
        packages = self._index_map.get("packages", {})
        if package_id not in packages:
            raise ValueError("Không tìm thấy gói Master Data.")
        if not name or len(name) > 80:
            raise ValueError("Tên gói phải có từ 1 đến 80 ký tự.")
        
        target_pkg_id = package_id
        if new_package_id:
            cleaned_new_id = re.sub(r"[^a-zA-Z0-9_]", "_", str(new_package_id)).lower().strip("_")
            if cleaned_new_id and cleaned_new_id != package_id:
                if cleaned_new_id in packages:
                    raise ValueError(f"Mã gói '{cleaned_new_id}' đã tồn tại, vui lòng chọn mã khác.")
                
                # Move json file if exists
                old_info = packages.pop(package_id)
                old_file = self.storage_dir / (old_info.get("file") or f"{package_id}.json")
                new_file = self.storage_dir / f"{cleaned_new_id}.json"
                if old_file.is_file():
                    try:
                        # Update inside json
                        try:
                            with open(old_file, "r", encoding="utf-8") as f:
                                json_content = json.load(f)
                            json_content["package_id"] = cleaned_new_id
                            json_content["display_name"] = name
                            with open(new_file, "w", encoding="utf-8") as f:
                                json.dump(json_content, f, ensure_ascii=False, indent=2)
                            old_file.unlink()
                        except Exception:
                            if old_file.exists() and not new_file.exists():
                                old_file.rename(new_file)
                    except Exception as e:
                        print(f"[RefMasterService] Lỗi đổi file json: {e}")
                
                old_info["file"] = f"{cleaned_new_id}.json"
                old_info["display_name"] = name
                packages[cleaned_new_id] = old_info
                
                # Update restaurants mapping
                restaurants = self._index_map.get("restaurants", {})
                for r_id, r_info in restaurants.items():
                    if r_info.get("package_id") == package_id:
                        r_info["package_id"] = cleaned_new_id
                
                target_pkg_id = cleaned_new_id

        if target_pkg_id in packages:
            packages[target_pkg_id]["display_name"] = name
            # Update json inside
            target_json = self.storage_dir / (packages[target_pkg_id].get("file") or f"{target_pkg_id}.json")
            if target_json.is_file():
                try:
                    with open(target_json, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["display_name"] = name
                    with open(target_json, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        self._save_index()
        return {"success": True, "package_id": target_pkg_id, "display_name": name}

    def delete_package(self, package_id: str) -> Dict[str, Any]:
        """Xóa gói Master Data cùng file json và gỡ các ánh xạ nhà hàng tương ứng."""
        package_id = str(package_id)
        self._index_map = self._load_index()
        packages = self._index_map.get("packages", {})
        if package_id not in packages:
            raise ValueError("Không tìm thấy gói Master Data để xóa.")
        
        info = packages.pop(package_id)
        file_name = info.get("file") or f"{package_id}.json"
        target_file = self.storage_dir / file_name
        if target_file.is_file():
            try:
                target_file.unlink()
            except Exception:
                pass

        restaurants = self._index_map.get("restaurants", {})
        to_del = [r_id for r_id, r_info in restaurants.items() if r_info.get("package_id") == package_id]
        for r_id in to_del:
            del restaurants[r_id]

        self._save_index()
        return {"success": True, "package_id": package_id}
