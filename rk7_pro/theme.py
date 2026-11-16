"""Shared visual tokens for the RK7 Pro desktop interface."""

APP_BG = "#F4F7FB"
SIDEBAR_BG = "#FFFFFF"
PANEL_BG = "#FFFFFF"
CARD_BG = "#FFFFFF"
CARD_HOVER = "#F8FAFC"
SUBTLE_BG = "#F8FAFC"
EDITOR_BG = "#111827"
BORDER_COLOR = "#E2E8F0"
DIVIDER_COLOR = "#EDF1F5"

# Kept under the old name for compatibility with existing components.
NEON_GREEN = "#10B981"
NEON_GREEN_HOVER = "#FEF2F2"
BRAND_RED = "#3B82F6"
BRAND_RED_DARK = "#2563EB"
ACCENT_PINNED = "#F59E0B"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
INFO = "#3B82F6"

TEXT_MAIN = "#142033"
TEXT_SEC = "#475569"
TEXT_MUTED = "#94A3B8"
TEXT_BLACK = "#0F172A"

AVATAR_COLORS = {
    "emerald": "#10B981",
    "teal": "#14B8A6",
    "blue": "#3B82F6",
    "purple": "#8B5CF6",
    "orange": "#F59E0B",
}

FONT_FAMILY = "Barlow, 'Segoe UI', -apple-system, sans-serif"
FONT_MONO = "Consolas, 'JetBrains Mono', monospace"

GLOBAL_QSS = f"""
QMainWindow {{
    background-color: palette(window);
}}
QWidget {{
    font-family: {FONT_FAMILY};
    color: palette(text);
}}
QPushButton, QLineEdit, QPlainTextEdit {{
    outline: none;
}}
QPushButton:focus {{
    border: 1px solid {BRAND_RED};
}}
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 8px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #CBD5E1;
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: #94A3B8;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
}}
QToolTip {{
    background-color: palette(tool-tip-base);
    color: palette(tool-tip-text);
    border: none;
    border-radius: 8px;
    padding: 7px 10px;
    font-size: 11px;
}}
QMenu {{
    background-color: palette(base);
    color: palette(text);
    border: 1px solid palette(mid);
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    min-height: 30px;
    padding: 2px 16px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {NEON_GREEN_HOVER};
    color: {BRAND_RED_DARK};
}}
"""