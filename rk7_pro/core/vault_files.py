"""Safe file and draft operations for Script Vault."""
import hashlib
import json
import os
import shutil
import tempfile
import time
import uuid
from pathlib import Path


class VaultFiles:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.draft_dir = self.root / ".rk7_vault_drafts"
        self.history_file = self.root / ".rk7_vault_history.jsonl"

    def checked(self, path, exists=True):
        target = Path(path).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ValueError("File must be inside the current Vault")
        if exists and not target.is_file():
            raise FileNotFoundError(target)
        return target

    @staticmethod
    def _decode(raw):
        if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
            return raw.decode("utf-16"), "utf-16"
        if raw.startswith(b"\xef\xbb\xbf"):
            return raw.decode("utf-8-sig"), "utf-8-sig"
        for encoding in ("utf-8", "cp1252"):
            try:
                return raw.decode(encoding), encoding
            except UnicodeDecodeError:
                pass
        raise UnicodeError("Unsupported file encoding")

    def read(self, path):
        target = self.checked(path)
        raw = target.read_bytes()
        content, encoding = self._decode(raw)
        newline = "\r\n" if "\r\n" in content and content.count("\r\n") == content.count("\n") else "\r" if "\r" in content and "\n" not in content else "\n"
        stat = target.stat()
        return {"content": content, "encoding": encoding, "newline": newline,
                "hash": hashlib.sha256(raw).hexdigest(), "modified": stat.st_mtime,
                "size_bytes": stat.st_size, "line_count": len(content.splitlines())}

    def write(self, path, content, expected_hash, encoding, newline="\n"):
        target = self.checked(path)
        raw = target.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_hash:
            raise ValueError("File changed outside RK7 PRO. Reload or Save As before saving.")
        if encoding not in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
            raise ValueError("Unsupported encoding")
        if newline not in ("\n", "\r\n", "\r"):
            raise ValueError("Unsupported newline")
        normalized = content.replace("\r\n", "\n").replace("\r", "\n")
        payload = normalized.replace("\n", newline).encode(encoding)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".rk7-", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            shutil.copystat(target, temporary)
            os.replace(temporary, target)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
        return self.read(target)

    def draft_path(self, path):
        target = self.checked(path)
        return self.draft_dir / (hashlib.sha256(str(target).casefold().encode()).hexdigest() + ".json")

    def save_draft(self, path, content, base_hash):
        draft = self.draft_path(path)
        draft.parent.mkdir(exist_ok=True)
        payload = {"path": str(self.checked(path)), "content": content,
                   "base_hash": base_hash, "saved_at": time.time()}
        temp = draft.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            os.replace(temp, draft)
        except PermissionError:
            shutil.copyfile(temp, draft)
            temp.unlink(missing_ok=True)
        return True

    def get_draft(self, path):
        draft = self.draft_path(path)
        if not draft.exists():
            return None
        try:
            data = json.loads(draft.read_text(encoding="utf-8"))
            return data if data.get("path") == str(self.checked(path)) else None
        except (OSError, ValueError):
            return None

    def discard_draft(self, path):
        self.draft_path(path).unlink(missing_ok=True)
        return True

    def destination(self, source, name):
        source = self.checked(source)
        name = str(name).strip()
        if not name or name in (".", "..") or Path(name).name != name or any(c in name for c in '<>:"/\\|?*'):
            raise ValueError("Invalid file name")
        target = self.checked(source.with_name(name), exists=False)
        if target.suffix.lower() != source.suffix.lower():
            raise ValueError("Keep the original file extension")
        if target.exists():
            raise FileExistsError("A file with this name already exists")
        return target

    def duplicate(self, source, name):
        target = self.destination(source, name)
        shutil.copy2(source, target)
        return str(target)

    def rename(self, source, name):
        target = self.destination(source, name)
        Path(source).rename(target)
        return str(target)

    def delete_to_trash(self, source):
        source = self.checked(source)
        trash = self.root / ".rk7_vault_trash"
        trash.mkdir(exist_ok=True)
        target = trash / (uuid.uuid4().hex + "__" + source.name)
        shutil.move(str(source), target)
        return str(target)

    def log(self, path, event, previous_path=None):
        record = {"path": str(Path(path).resolve()), "event": event, "timestamp": time.time()}
        if previous_path:
            record["previous_path"] = str(Path(previous_path).resolve())
        with self.history_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def history(self, path):
        target = str(self.checked(path))
        if not self.history_file.exists():
            return []
        all_records = []
        with self.history_file.open("r", encoding="utf-8") as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                    all_records.append(record)
                except ValueError:
                    pass
        paths = {target}
        for record in reversed(all_records):
            if record.get("event") == "Renamed" and record.get("path") in paths:
                paths.add(record.get("previous_path"))
        records = [record for record in all_records if record.get("path") in paths]
        return records[-100:][::-1]
