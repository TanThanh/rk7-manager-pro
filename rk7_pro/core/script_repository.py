# rk7_pro/core/script_repository.py
import os
import json
import re
import shutil
from pathlib import Path
from datetime import datetime

class ScriptSnippet:
    def __init__(self, file_path: Path, meta: dict = None):
        self.file_path = file_path
        self.filename = file_path.name
        self.name = file_path.stem
        self.suffix = file_path.suffix.lower()
        self.rel_folder = file_path.parent.name
        self.size_bytes = 0
        self.modified_time = 0.0
        self.created_time = 0.0
        self.preview_snippet = ""
        self.content = ""
        self.line_count = 0
        self.file_type = self._detect_file_type()
        
        # Metadata
        self.meta = meta or {}
        self.title = self.meta.get("title", self.filename)
        self.description = self.meta.get("description", "")
        self.tags = self.meta.get("tags", [])
        self.is_favorite = self.meta.get("is_favorite", False)
        self.last_viewed = self.meta.get("last_viewed", 0.0)

        self.refresh()
        self.file_type = self.meta.get("language") or self.file_type

    def _detect_file_type(self) -> str:
        s = self.suffix
        if s == ".sql":
            return "SQL"
        elif s == ".py":
            return "Python"
        elif s in (".bat", ".cmd"):
            return "Batch"
        elif s == ".ps1":
            return "PowerShell"
        elif s in (".pas", ".dps"):
            return "Delphi"
        elif s in (".sh", ".bash"):
            return "Shell"
        elif s == ".json":
            return "JSON"
        elif s == ".xml":
            return "XML"
        elif s in (".ini", ".cfg", ".conf"):
            return "Config"
        elif s in (".txt", ".text", ".log", ".md"):
            # Text files often contain scripts with a different extension.
            try:
                with open(self.file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    sample = f.read(16384).lstrip("\ufeff \t\r\n")
                # Ignore SQL comments before looking for a statement at a line start.
                without_comments = re.sub(r"/\*.*?\*/|^\s*--[^\n]*", "", sample, flags=re.S | re.M)
                sql_statement = (
                    r"SELECT\b|INSERT\s+INTO\b|UPDATE\s+\S+\s+SET\b|"
                    r"DELETE\s+FROM\b|CREATE\s+(?:OR\s+ALTER\s+)?"
                    r"(?:TABLE|VIEW|PROCEDURE|PROC|FUNCTION|INDEX|TRIGGER)\b|"
                    r"ALTER\s+(?:TABLE|VIEW|PROCEDURE|PROC|FUNCTION)\b|"
                    r"DROP\s+(?:TABLE|VIEW|PROCEDURE|PROC|FUNCTION|INDEX)\b|"
                    r"DECLARE\s+@|EXEC(?:UTE)?\s+|MERGE\s+INTO\b|"
                    r"WITH\s+\w+\s+AS\s*\("
                )
                if re.search(rf"(?im)^\s*(?:{sql_statement})", without_comments):
                    return "SQL"
                if re.match(r"(?is)^<\?xml\b|^<[A-Za-z_][\w:.-]*(?:\s|>|/>)", sample):
                    return "XML"
                if re.match(r"(?im)^(?:@echo\s+off\b|echo\s+off\b|::|rem\s+)", sample):
                    return "Batch"
                if re.search(r"(?im)^\s*(?:procedure|function)\s+\w+|\bTCheckItem\b|^\s*begin\s*$", sample):
                    return "Delphi"
                if re.search(r"(?im)^\s*(?:Get-Process|Start-Process|Write-Host)\b", sample):
                    return "PowerShell"
            except Exception:
                pass
            return "Text"
        return "Script"

    def refresh(self):
        if not self.file_path.exists():
            return
        self.file_type = self._detect_file_type()
        stat = self.file_path.stat()
        self.size_bytes = stat.st_size
        self.modified_time = stat.st_mtime
        self.created_time = stat.st_ctime
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(8)]
                preview = "".join(lines).strip()
                # If description is empty, try to extract first meaningful comment
                if not self.description:
                    for line in lines:
                        cleaned = line.strip()
                        if cleaned.startswith(("--", "//", "#", "::", "/*")):
                            desc = re.sub(r"^(--|//|#|::|/\*)\s*", "", cleaned).rstrip("*/").strip()
                            if (desc and not re.match(r"^[-=*_#]{3,}$", desc)
                                    and not re.match(r"^[a-zA-Z0-9_]+\s*:\s*[a-zA-Z0-9_]+;", desc)):
                                self.description = desc
                                break
                self.preview_snippet = (preview[:160] + "...") if len(preview) > 160 else preview
        except Exception:
            self.preview_snippet = ""

    def load_full_content(self) -> str:
        try:
            with open(self.file_path, "r", encoding="utf-8", errors="replace") as f:
                self.content = f.read()
                self.line_count = len(self.content.splitlines())
                return self.content
        except Exception as e:
            self.content = f"Error reading file: {e}"
            return self.content

    def save_content(self, text: str) -> bool:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                f.write(text)
            self.content = text
            self.refresh()
            return True
        except Exception:
            return False

    def get_created_str(self) -> str:
        try:
            t = self.created_time or self.modified_time
            return datetime.fromtimestamp(t).strftime("%H:%M %d/%m/%Y")
        except Exception:
            return "--:-- --/--/----"

    def get_modified_str(self) -> str:
        try:
            return datetime.fromtimestamp(self.modified_time).strftime("%H:%M %d/%m/%Y")
        except Exception:
            return "--:-- --/--/----"


class ScriptRepository:
    SUPPORTED_EXTENSIONS = {
        ".sql", ".txt", ".text", ".py", ".bat", ".cmd", ".ps1", ".pas", ".dps", ".sh", ".json", ".xml", ".ini", ".cfg", ".md"
    }
    NEW_SCRIPT_EXTENSIONS = {
        "SQL": ".sql", "Python": ".py", "Batch": ".bat",
        "PowerShell": ".ps1", "Delphi": ".pas", "XML": ".xml", "Text": ".txt",
        "JSON": ".json", "Shell": ".sh", "Markdown": ".md",
    }

    def __init__(self, vault_dir: str):
        self.vault_dir = Path(vault_dir)
        self.metadata_file = self.vault_dir / ".vault_meta.json"
        self._meta_cache = {}
        self._ensure_default_vault()
        self.snippets = []

    def _load_meta(self):
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    self._meta_cache = json.load(f)
            except Exception:
                self._meta_cache = {}
        else:
            self._meta_cache = {}

    def _meta_key(self, path: Path) -> str:
        return path.resolve().relative_to(self.vault_dir.resolve()).as_posix()

    def _meta_for(self, path: Path) -> dict:
        # Keep reading legacy filename keys; new edits use relative paths so
        # same-named files in different folders no longer share metadata.
        return self._meta_cache.get(self._meta_key(path), self._meta_cache.get(path.name, {}))

    def _editable_meta(self, snippet: ScriptSnippet) -> dict:
        key = self._meta_key(snippet.file_path)
        if key not in self._meta_cache:
            self._meta_cache[key] = dict(self._meta_for(snippet.file_path))
        return self._meta_cache[key]

    def _save_meta(self):
        try:
            temp = self.metadata_file.with_suffix(".json.tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self._meta_cache, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.replace(temp, self.metadata_file)
            except PermissionError:
                # Some Windows managed/temp folders allow writes but reject
                # rename/replace. Keep the previous file as a recovery copy.
                if self.metadata_file.exists():
                    shutil.copy2(self.metadata_file, self.metadata_file.with_suffix(".json.bak"))
                shutil.copyfile(temp, self.metadata_file)
                temp.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    def _ensure_default_vault(self):
        try:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
            self._load_meta()
        except Exception:
            pass

    def _seed_sample_scripts(self):
        sql_folder = self.vault_dir / "SQL Queries"
        sql_folder.mkdir(exist_ok=True)
        
        sample_1 = sql_folder / "XOA_CA_CHUNG_TREN_DATABASE.sql"
        sample_1.write_text(
            "-- Script dung de xoa ca chung tren database cua nha hang khi bi lech gio\n"
            "-- Chu y sao luu DB truoc khi thuc hien\n"
            "DELETE FROM GLOBALSHIFTS\n"
            "WHERE SHIFTDATE = '2026-10-09' AND MIDSERVER = 1;\n",
            encoding="utf-8"
        )
        self._meta_cache[sample_1.name] = {
            "title": "XÓA CA CHUNG TRÊN DATABASE",
            "description": "Script dùng để xóa ca chung trên database của nhà hàng khi bị lỗi lệch giờ hoặc kẹt ca.",
            "tags": ["#DELETE_CACHUNG", "#SHIFTDATE", "#DATABASE"],
            "is_favorite": True
        }

        sample_2 = sql_folder / "SCRIPT_CHECK_DATA_SKYMONITOR_VS_RK7.sql"
        sample_2.write_text(
            "-- Script dung so sanh du lieu cua Skymonitor va RK7 (sau khi dong ca chung) xem co bi lech hay khong\n"
            "SELECT \n"
            "    RK.IRESTAURANT   AS RestaurantId,\n"
            "    R.NAME           AS RestaurantName,\n"
            "    RK.SHIFTDATE     AS ShiftDate,\n"
            "    RK.MIDSERVER,\n"
            "    RK.SHIFTNUM,\n"
            "    RK.PAYSUM        AS RK_PAYSUM,\n"
            "    SK.PAYSUM        AS SK_PAYSUM,\n"
            "    RK.PAYSUM - ISNULL(SK.PAYSUM, 0) AS DIFF_PAYSUM\n"
            "FROM (\n"
            "    SELECT \n"
            "        GS.IRESTAURANT,\n"
            "        GS.SHIFTDATE,\n"
            "        GS.MIDSERVER,\n"
            "        GS.SHIFTNUM,\n"
            "        SUM(PB.PAYSUM) AS PAYSUM\n"
            "    FROM GLOBALSHIFTS GS\n"
            "    LEFT JOIN ORDERS O ON O.MIDSERVER = GS.MIDSERVER AND O.ICOMMONSHIFT = GS.SHIFTNUM\n"
            "    LEFT JOIN PRINTCHECKS PC ON PC.MIDSERVER = O.MIDSERVER AND PC.VISIT = O.VISIT\n"
            "    WHERE PC.STATE = 6\n"
            "    GROUP BY GS.IRESTAURANT, GS.SHIFTDATE, GS.MIDSERVER, GS.SHIFTNUM\n"
            ") RK\n"
            "LEFT JOIN SKYMONITOR_PAYMENTS SK ON SK.MIDSERVER = RK.MIDSERVER AND SK.SHIFTNUM = RK.SHIFTNUM\n"
            "ORDER BY RK.SHIFTDATE DESC;\n",
            encoding="utf-8"
        )
        self._meta_cache[sample_2.name] = {
            "title": "SCRIPT CHECK DATA SKYMONITOR VS RK7",
            "description": "Script dùng so sánh dữ liệu của Skymonitor và RK7 (sau khi đóng ca chung) xem có bị lệch hay không.",
            "tags": ["#SKYMONITOR", "#RK7", "#DATA", "#CACHUNG"],
            "is_favorite": False
        }

        sample_3 = sql_folder / "SCRIPT_CHECK_XEM_SHIFTNUM_CO_BI_TRUNG.sql"
        sample_3.write_text(
            "-- Dung de kiem tra 1 nha co bi trung ca chung, nhung ca chung bi trung\n"
            "SELECT RESTAURANT_ID, SHIFTDATE, SHIFTNUM, COUNT(*)\n"
            "FROM GLOBALSHIFTS\n"
            "GROUP BY RESTAURANT_ID, SHIFTDATE, SHIFTNUM\n"
            "HAVING COUNT(*) > 1;\n",
            encoding="utf-8"
        )
        self._meta_cache[sample_3.name] = {
            "title": "SCRIPT CHECK XEM SHIFTNUM CÓ BỊ TRÙNG",
            "description": "Dùng để kiểm tra 1 nhà có bị trùng ca chung, nhận diện những ca chung bị trùng lặp.",
            "tags": ["#SQL", "#CHECK_SHIFTNUM", "#TRUNG_SHIFT"],
            "is_favorite": False
        }

        self._save_meta()

    def set_vault_dir(self, new_dir: str) -> bool:
        p = Path(new_dir)
        try:
            p.mkdir(parents=True, exist_ok=True)
            self.vault_dir = p
            self.metadata_file = self.vault_dir / ".vault_meta.json"
            self._load_meta()
            self.scan()
            return True
        except Exception:
            return False

    def list_folders(self) -> list[str]:
        root = self.vault_dir.resolve()
        return sorted(
            (str(path.relative_to(root)).replace("\\", "/")
             for path in root.rglob("*") if path.is_dir() and not path.name.startswith(".")),
            key=str.casefold,
        )

    def create_script(self, name: str, file_type: str, folder: str, content: str) -> ScriptSnippet:
        extension = self.NEW_SCRIPT_EXTENSIONS.get(file_type)
        if extension is None:
            raise ValueError("Choose a supported script type.")

        name = name.strip()
        if name.lower().endswith(extension):
            name = name[:-len(extension)].rstrip()
        elif Path(name).suffix.lower() in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Remove the existing extension or choose its matching type ({extension}).")
        if not name or name in (".", "..") or name.endswith((".", " ")):
            raise ValueError("Enter a valid file name.")
        if any(char in name for char in '<>:"/\\|?*') or any(ord(char) < 32 for char in name):
            raise ValueError("File name contains invalid characters.")
        if name.split(".", 1)[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}:
            raise ValueError("This file name is reserved by Windows.")

        root = self.vault_dir.resolve()
        relative_folder = Path(folder or ".")
        destination_dir = (root / relative_folder).resolve()
        if relative_folder.is_absolute() or not destination_dir.is_relative_to(root) or not destination_dir.is_dir():
            raise ValueError("Choose a folder inside the Script Vault.")

        destination = destination_dir / f"{name}{extension}"
        with destination.open("x", encoding="utf-8") as file:
            file.write(content)
        snippet = ScriptSnippet(destination)
        snippet.load_full_content()
        self.snippets.append(snippet)
        return snippet

    def scan(self) -> list:
        self.snippets = []
        if not self.vault_dir.exists():
            return self.snippets

        self._load_meta()
        try:
            for root, dirs, files in os.walk(self.vault_dir):
                # Don't recurse into hidden directories or system vault folders
                dirs[:] = [d for d in dirs if not d.startswith(".") and d not in (".rk7_vault_trash", ".rk7_vault_drafts", ".rk7_vault_backups")]
                for file in files:
                    if file.startswith("."):
                        continue
                    file_path = Path(root) / file
                    if file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                        meta = self._meta_for(file_path)
                        snippet = ScriptSnippet(file_path, meta)
                        self.snippets.append(snippet)
        except Exception:
            pass

        self.snippets.sort(key=lambda s: s.filename.lower())
        return self.snippets

    def update_snippet_meta(self, snippet: ScriptSnippet, title: str, description: str, tags: list):
        snippet.title = title
        snippet.description = description
        snippet.tags = tags
        self._meta_cache[self._meta_key(snippet.file_path)] = {**self._editable_meta(snippet),
            "title": title,
            "description": description,
            "tags": tags,
            "is_favorite": snippet.is_favorite,
            "last_viewed": snippet.last_viewed
        }
        self._save_meta()

    def toggle_favorite(self, snippet: ScriptSnippet) -> bool:
        snippet.is_favorite = not snippet.is_favorite
        self._editable_meta(snippet)["is_favorite"] = snippet.is_favorite
        self._save_meta()
        return snippet.is_favorite

    def record_viewed(self, snippet: ScriptSnippet):
        import time
        snippet.last_viewed = time.time()
        self._editable_meta(snippet)["last_viewed"] = snippet.last_viewed
        self._save_meta()

    def get_all_tags(self) -> list:
        tag_counts = {}
        for s in self.snippets:
            for t in s.tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        return sorted(tag_counts.items(), key=lambda x: -x[1])

    def filter(self, query: str = "", nav_filter: str = "all", tag_filter: str = None) -> list:
        results = self.snippets

        # Navigation filter (all, favorite, recent)
        if nav_filter == "favorite":
            results = [s for s in results if s.is_favorite]
        elif nav_filter == "recent":
            results = [s for s in results if s.last_viewed > 0]
            results.sort(key=lambda s: s.last_viewed, reverse=True)

        # Tag filter
        if tag_filter:
            results = [s for s in results if tag_filter in s.tags]

        # Search query
        if query:
            q = query.lower().strip()
            def match(s: ScriptSnippet):
                if q in s.filename.lower() or q in s.title.lower():
                    return True
                if q in s.description.lower():
                    return True
                if any(q in t.lower() for t in s.tags):
                    return True
                if q in s.preview_snippet.lower():
                    return True
                return False
            results = [s for s in results if match(s)]

        return results

    def add_new_snippet(self, filename: str, content: str, title: str = "", tags: list = None) -> ScriptSnippet:
        target_file = self.vault_dir / filename
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        meta = {
            "title": title or target_file.stem,
            "description": "",
            "tags": tags or ["#SQL" if ScriptSnippet(target_file).file_type == "SQL" else "#SCRIPT"],
            "is_favorite": False
        }
        self._meta_cache[filename] = meta
        self._save_meta()
        snippet = ScriptSnippet(target_file, meta)
        self.snippets.append(snippet)
        return snippet

    def import_files(self, file_paths: list, collision: str = "rename") -> int:
        import shutil
        imported_count = 0
        self.last_imported_paths = []
        self.last_import_existing = 0
        self.last_import_errors = []
        for src in file_paths:
            src_p = Path(src)
            if not src_p.is_file():
                self.last_import_errors.append(f"File not found: {src_p}")
                continue
            if src_p.suffix.lower() not in self.SUPPORTED_EXTENSIONS:
                self.last_import_errors.append(f"Unsupported file type: {src_p.name}")
                continue
            dest_p = self.vault_dir / src_p.name
            if src_p.resolve() == dest_p.resolve():
                self.last_import_existing += 1
                continue
            if dest_p.exists():
                if collision == "skip":
                    self.last_import_existing += 1
                    continue
                if collision == "rename":
                    index = 2
                    while dest_p.exists():
                        dest_p = self.vault_dir / f"{src_p.stem} ({index}){src_p.suffix}"
                        index += 1
                elif collision != "replace":
                    self.last_import_errors.append("Invalid collision policy")
                    continue
            try:
                if dest_p.exists():
                    backup = self.vault_dir / ".rk7_vault_backups"
                    backup.mkdir(exist_ok=True)
                    shutil.copy2(dest_p, backup / f"{int(datetime.now().timestamp() * 1000000)}__{dest_p.name}")
                shutil.copy2(src_p, dest_p)
                key = self._meta_key(dest_p)
                if key not in self._meta_cache and dest_p.name not in self._meta_cache:
                    detected_type = ScriptSnippet(dest_p).file_type
                    tag = "#SQL" if detected_type == "SQL" else ("#BATCH" if detected_type in ("Batch", "PowerShell") else "#SCRIPT")
                    self._meta_cache[key] = {
                        "title": dest_p.stem.replace("_", " ").upper(),
                        "description": "",
                        "tags": [tag],
                        "is_favorite": False
                    }
                imported_count += 1
                self.last_imported_paths.append(dest_p)
            except Exception as e:
                self.last_import_errors.append(f"{src_p.name}: {e}")
        if imported_count > 0:
            self._save_meta()
            self.scan()
        return imported_count

    def import_from_folder(self, source_folder: str) -> int:
        p = Path(source_folder)
        if not p.exists() or not p.is_dir():
            return 0
        files = []
        for root, _, fs in os.walk(p):
            for f in fs:
                if not f.startswith("."):
                    files.append(Path(root) / f)
        return self.import_files(files)

    def rename_snippet(self, snippet: ScriptSnippet, new_title: str) -> bool:
        new_title = new_title.strip()
        if not new_title:
            return False
        snippet.title = new_title
        self._editable_meta(snippet)["title"] = new_title
        self._save_meta()
        return True

    def delete_snippet(self, snippet: ScriptSnippet) -> bool:
        try:
            if snippet.file_path.exists():
                snippet.file_path.unlink()
            if snippet in self.snippets:
                self.snippets.remove(snippet)
            if snippet.filename in self._meta_cache:
                del self._meta_cache[snippet.filename]
                self._save_meta()
            return True
        except Exception:
            return False
