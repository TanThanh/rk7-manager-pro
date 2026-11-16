from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit
from PySide6.QtCore import Qt, Signal as pyqtSignal
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import TEXT_MAIN, TEXT_MUTED, BRAND_RED, BORDER_COLOR
from rk7_pro.components.icons import VectorIcon
from rk7_pro.theme_manager import theme_color


class SearchBar(QFrame):
    text_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setFixedHeight(50)
        self.setProperty("_rk7_theme_static", True)
        self._set_focused(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 14, 0)
        layout.setSpacing(12)

        self.icon_widget = VectorIcon("search", color="#64748B", size=19, parent=self)
        layout.addWidget(self.icon_widget)

        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Search by shortcut name or path...")
        self.input_field.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.input_field.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #F8FAFC;
                font-size: 14px;
                padding: 0;
            }
            QLineEdit::placeholder {
                color: #64748B;
            }
        """)
        self.input_field.textChanged.connect(self.text_changed.emit)
        self.input_field.focusInEvent = self._on_focus_in
        self.input_field.focusOutEvent = self._on_focus_out
        layout.addWidget(self.input_field)

        self.hint_lbl = QLabel("CTRL  F", self)
        self.hint_lbl.setStyleSheet(
            "color: #94A3B8; background: #181C24; border: 1px solid #2B3240; "
            "border-radius: 6px; padding: 3px 8px; font-size: 9px; font-weight: 700;"
        )
        layout.addWidget(self.hint_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

    def _set_focused(self, focused):
        self.setStyleSheet(f"""
            QFrame {{
                background: #13161C;
                border: {'1.5px' if focused else '1px'} solid {'#3B82F6' if focused else '#1E232D'};
                border-radius: 10px;
            }}
        """)

    def _on_focus_in(self, event):
        self._set_focused(True)
        self.icon_widget.set_color(BRAND_RED)
        QLineEdit.focusInEvent(self.input_field, event)

    def _on_focus_out(self, event):
        self._set_focused(False)
        self.icon_widget.set_color(TEXT_MUTED)
        QLineEdit.focusOutEvent(self.input_field, event)

    def setFocus(self):
        self.input_field.setFocus()
