"""Runtime light/dark theme support for the RK7 Pro widget tree."""

import re
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

from rk7_pro.theme import GLOBAL_QSS


_DARK_MODE = False

LIGHT_TO_DARK = {
    "#F4F7FB": "#09090B",
    "#FFFFFF": "#13161C",
    "#F8FAFC": "#181B22",
    "#142033": "#F8FAFC",
    "#0F172A": "#F8FAFC",
    "#475569": "#94A3B8",
    "#94A3B8": "#64748B",
    "#E2E8F0": "#1E232D",
    "#EDF1F5": "#151820",
    "#CBD5E1": "#333A48",
    "#FEF2F2": "#2A1820",
    "#FECACA": "#5B222E",
    "#FFF7ED": "#2A1F10",
    "#FFEDD5": "#452C12",
    "#FFF8F8": "#26161B",
    "#F7FFFC": "#0D231C",
    "#ECFDF5": "#0A241D",
    "#A7F3D0": "#134E35",
    "#FFFBEB": "#292010",
    "#FDE68A": "#78440E",
    "#FEE2E2": "#3B1820",
    "#FCA5A5": "#EF4444",
}


def is_dark_mode():
    return _DARK_MODE


def theme_color(color):
    if not _DARK_MODE or not isinstance(color, str):
        return color
    return LIGHT_TO_DARK.get(color.upper(), color)


def translate_stylesheet(stylesheet, dark=True):
    if not dark or not stylesheet:
        return stylesheet
    pattern = re.compile(
        "|".join(re.escape(color) for color in LIGHT_TO_DARK),
        flags=re.IGNORECASE,
    )
    return pattern.sub(lambda match: LIGHT_TO_DARK[match.group(0).upper()], stylesheet)


def _apply_palette(app, dark):
    if not dark:
        palette = app.style().standardPalette()
        # Keep tooltips consistently high-contrast regardless of the Windows theme.
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#142033"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F8FAFC"))
        app.setPalette(palette)
        return

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#09090B"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#0D0F12"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#13161C"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#181B22"))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#13161C"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F8FAFC"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#64748B"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#3B82F6"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)


def apply_widget_theme(root, dark, refresh_base=False):
    """Translate local styles in one paint-suppressed pass.

    Icon source colors are captured once and never resampled from hover/dark state.
    """
    widgets = [root] + root.findChildren(QWidget)
    root.setUpdatesEnabled(False)
    try:
        for widget in widgets:
            # Permanent dark shells (such as the sidebar) keep their authored
            # contrast instead of passing ambiguous colors through translation.
            current_parent = widget
            theme_static = False
            while current_parent is not None:
                if current_parent.property("_rk7_theme_static"):
                    theme_static = True
                    break
                if current_parent is root:
                    break
                current_parent = current_parent.parentWidget()
            if theme_static:
                continue

            current = widget.styleSheet()
            base = widget.property("_rk7_light_style")

            if base is None:
                if not current:
                    continue
                base = current
                widget.setProperty("_rk7_light_style", base)
                widget.setProperty("_rk7_dark_style", translate_stylesheet(base, True))
            elif refresh_base:
                expected = translate_stylesheet(base, True)
                if current not in (base, expected):
                    base = current
                    widget.setProperty("_rk7_light_style", base)

            target = widget.property("_rk7_dark_style") if dark else base
            if current != target:
                widget.setStyleSheet(target)


    finally:
        root.setUpdatesEnabled(True)
        root.update()


def set_dark_mode(root, dark):
    global _DARK_MODE
    _DARK_MODE = bool(dark)
    app = QApplication.instance()
    if app:
        _apply_palette(app, _DARK_MODE)

    apply_widget_theme(root, _DARK_MODE)