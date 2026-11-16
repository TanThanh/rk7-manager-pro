# rk7_pro/core/shortcut_repository.py
import json
import sys
import os
import subprocess
import hashlib
import shutil
from pathlib import Path
from PySide6.QtCore import QObject, Signal as pyqtSignal, QThread

try:
    import winshell
    import pythoncom
    WIN_ENV = True
except ImportError:
    WIN_ENV = False

from rk7_pro.core.models import ShortcutState

class ShortcutRepository(QObject):
    state_changed = pyqtSignal(str, ShortcutState)  # filename, new_state
    store_ready = pyqtSignal()

    def __init__(self, shortcut_dir_str):
        super().__init__()
        self.shortcut_dir = Path(shortcut_dir_str)
        if getattr(sys, 'frozen', False):
            bundle_dir = Path(sys.executable).parent
        else:
            bundle_dir = Path(__file__).parent.parent
            
        self.bundle_dir = bundle_dir
        self.background_dir = bundle_dir / "card_backgrounds"
        self.fav_file = bundle_dir / "favorites.json"
        self.custom_file = bundle_dir / "customization.json"
        
        self.states = {}  # Dict[str, ShortcutState] mappings by filename

    def update_root_folder(self, new_dir):
        path = Path(new_dir)
        if path.exists() and path.is_dir():
            self.shortcut_dir = path
            self.states.clear()
            self.initialize()
            return True
        return False

    def initialize(self):
        favorites = self._load_favorites()
        customs = self._load_customizations()
        if not self.shortcut_dir.exists():
            return
            
        files = [f.name for f in self.shortcut_dir.iterdir() if f.suffix.lower() == '.lnk']
        files.sort(key=lambda x: (x not in favorites, x.lower()))
        
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
                # Fallback for broken links or missing library support
                state = ShortcutState(
                    id=filename,
                    name=filename.replace('.lnk', ''),
                    is_pinned=(filename in favorites)
                )
                
            # Apply customizations
            if filename in customs:
                c = customs[filename]
                state.custom_name = c.get("name")
                state.custom_color = c.get("color")
                state.custom_icon = c.get("icon")
                state.custom_background = self._resolve_background(c.get("background"))
                
            self.states[filename] = state
            
        if WIN_ENV and has_com:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
            
        self.store_ready.emit()

    def _load_favorites(self):
        if self.fav_file.exists():
            try:
                with open(self.fav_file, "r") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def toggle_favorite(self, filename):
        state = self.states.get(filename)
        if state:
            state.is_pinned = not state.is_pinned
            self._save_favorites()
            self.state_changed.emit(filename, state)

    def _save_favorites(self):
        favs = [sid for sid, state in self.states.items() if state.is_pinned]
        try:
            with open(self.fav_file, "w") as f:
                json.dump(favs, f)
        except Exception:
            pass

    def get_all(self):
        return list(self.states.values())

    def get_by_id(self, state_id):
        return self.states.get(state_id)

    def update_state(self, filename, **kwargs):
        state = self.states.get(filename)
        if state:
            for k, v in kwargs.items():
                setattr(state, k, v)
            self.state_changed.emit(filename, state)
            
    def get_ini_content(self, filename):
        state = self.states.get(filename)
        if not state or not state.target_exe_path:
            return "[Not Found] Invalid shortcut data.", None
            
        ini_path = Path(state.target_exe_path).parent / "rk7man.ini"
        if ini_path.exists():
            try:
                content = ini_path.read_text(encoding='utf-8', errors='replace')
                return content, ini_path
            except Exception as e:
                return f"[Error] {e}", None
        return "[Not Found] rk7man.ini does not exist in target dir.", None

    def _load_customizations(self):
        if hasattr(self, 'custom_file') and self.custom_file.exists():
            try:
                with open(self.custom_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _resolve_background(self, stored_value):
        if not stored_value:
            return None
        path = Path(stored_value)
        if not path.is_absolute():
            path = self.bundle_dir / path
        return str(path) if path.exists() and path.is_file() else None

    def _store_background(self, filename, source_path):
        if not source_path:
            return None, None
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            return None, None
        suffix = source.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            return None, None
        self.background_dir.mkdir(parents=True, exist_ok=True)
        try:
            source_resolved = source.resolve()
            background_resolved = self.background_dir.resolve()
            source_resolved.relative_to(background_resolved)
            destination = source_resolved
        except (OSError, ValueError):
            digest = hashlib.sha1(filename.encode("utf-8")).hexdigest()[:16]
            destination = self.background_dir / f"{digest}{suffix}"
            shutil.copy2(source, destination)
        relative = destination.relative_to(self.bundle_dir).as_posix()
        return str(destination), relative

    def save_customization(self, filename, name, color, icon=None, background=None):
        state = self.states.get(filename)
        if state:
            background_path, stored_background = self._store_background(filename, background)
            state.custom_name = name if name else None
            state.custom_color = color if color else None
            state.custom_icon = icon if icon else None
            state.custom_background = background_path

            customs = self._load_customizations()
            if not name and not color and not icon and not stored_background:
                if filename in customs:
                    del customs[filename]
            else:
                customs[filename] = {
                    "name": name,
                    "color": color,
                    "icon": icon,
                    "background": stored_background
                }

            try:
                with open(self.custom_file, "w", encoding="utf-8") as f:
                    json.dump(customs, f, indent=4)
            except Exception:
                pass

            self.state_changed.emit(filename, state)
