from functools import lru_cache
from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


PHOSPHOR_WEIGHTS = ("thin", "light", "regular", "bold", "fill", "duotone")
PHOSPHOR_PREFIX = "phosphor:"

# Existing application keys resolve to the closest official Phosphor glyph.
# Identity icons use duotone; operational UI icons use regular by default.
ICON_ALIASES = {
    "launch": ("regular", "rocket-launch"),
    "rocket": ("regular", "rocket-launch"),
    "folders": ("regular", "folder-open"),
    "folder": ("regular", "folder-open"),
    "settings": ("regular", "gear-six"),
    "gear": ("regular", "gear-six"),
    "bell": ("regular", "bell"),
    "notification": ("regular", "bell"),
    "user": ("regular", "user-circle"),
    "profile": ("regular", "user-circle"),
    "chevron_right": ("regular", "caret-right"),
    "chevron": ("regular", "caret-right"),
    "plus": ("regular", "plus"),
    "edit": ("regular", "pencil-simple"),
    "pencil": ("regular", "pencil-simple"),
    "save": ("regular", "floppy-disk"),
    "search": ("regular", "magnifying-glass"),
    "find": ("regular", "magnifying-glass"),
    "star": ("fill", "bookmark-simple"),
    "bookmark": ("regular", "bookmark-simple"),
    "bookmark_filled": ("fill", "bookmark-simple"),
    "file": ("regular", "file-text"),
    "document": ("regular", "file-text"),
    "close": ("regular", "x"),
    "x": ("regular", "x"),
    "cross": ("regular", "x"),
    "filter": ("regular", "funnel"),
    "grid": ("regular", "squares-four"),
    "list": ("regular", "list-bullets"),
    "arrow_left": ("regular", "arrow-left"),
    "back": ("regular", "arrow-left"),
    "arrow_right": ("regular", "arrow-right"),
    "forward": ("regular", "arrow-right"),
    "refresh": ("regular", "arrows-clockwise"),
    "reload": ("regular", "arrows-clockwise"),
    "rotate_cw": ("regular", "arrows-clockwise"),
    "storefront": ("duotone", "storefront"),
    "store": ("duotone", "storefront"),
    "coffee": ("duotone", "coffee"),
    "restaurant": ("duotone", "fork-knife"),
    "bridge": ("duotone", "bridge"),
    "building": ("duotone", "buildings"),
    "monitor": ("duotone", "monitor"),
    "server": ("duotone", "hard-drives"),
    "trash": ("regular", "trash"),
    "clear": ("regular", "trash"),
    "database": ("regular", "database"),
    "code": ("regular", "code"),
    "terminal": ("regular", "terminal-window"),
}


def _asset_root():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "rk7_pro" / "assets" / "phosphor"
    return Path(__file__).resolve().parent.parent / "assets" / "phosphor"


def make_phosphor_key(name, weight="regular"):
    weight = weight if weight in PHOSPHOR_WEIGHTS else "regular"
    return f"{PHOSPHOR_PREFIX}{weight}:{name.lower().replace('_', '-')}"


def parse_phosphor_key(icon_key):
    key = (icon_key or "").lower()
    if key.startswith(PHOSPHOR_PREFIX):
        parts = key.split(":", 2)
        if len(parts) != 3:
            return None
        _, weight, name = parts
        if weight not in PHOSPHOR_WEIGHTS:
            return None
        return weight, name.replace("_", "-")
    return ICON_ALIASES.get(key)


def phosphor_path(icon_key):
    parsed = parse_phosphor_key(icon_key)
    if not parsed:
        return None
    weight, name = parsed
    filename = f"{name}.svg" if weight == "regular" else f"{name}-{weight}.svg"
    path = _asset_root() / weight / filename
    return path if path.exists() else None


@lru_cache(maxsize=16)
def available_phosphor_names(weight="regular"):
    if weight not in PHOSPHOR_WEIGHTS:
        weight = "regular"
    folder = _asset_root() / weight
    if not folder.exists():
        return tuple()
    suffix = "" if weight == "regular" else f"-{weight}"
    names = []
    for path in folder.glob("*.svg"):
        stem = path.stem
        names.append(stem[:-len(suffix)] if suffix and stem.endswith(suffix) else stem)
    return tuple(sorted(names))


@lru_cache(maxsize=1024)
def _render_pixmap(path_text, color_text, width, height):
    path = Path(path_text)
    if not path.exists():
        return QPixmap()
    try:
        svg = path.read_bytes().replace(b"currentColor", color_text.encode("ascii"))
    except (OSError, UnicodeEncodeError):
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(svg))
    if not renderer.isValid():
        return QPixmap()
    scale = 2
    pixmap = QPixmap(max(1, width * scale), max(1, height * scale))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, pixmap.width(), pixmap.height()))
    painter.end()
    pixmap.setDevicePixelRatio(scale)
    return pixmap


def paint_phosphor_icon(painter, rect, icon_key, color):
    path = phosphor_path(icon_key)
    if path is None:
        return False
    qcolor = QColor(color)
    if not qcolor.isValid():
        return False
    color_text = qcolor.name()
    width = max(1, int(round(rect.width())))
    height = max(1, int(round(rect.height())))
    pixmap = _render_pixmap(str(path), color_text, width, height)
    if pixmap.isNull():
        return False
    # The cached pixmap already carries a 2x device-pixel ratio. Drawing it at
    # its logical origin avoids a second rescale through its physical rect,
    # which made thin SVG strokes look jagged and soft.
    painter.drawPixmap(rect.topLeft(), pixmap)
    return True