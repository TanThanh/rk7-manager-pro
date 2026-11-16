from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QFileDialog, QScrollArea, QWidget
)
from PySide6.QtCore import Qt, Signal as pyqtSignal
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import (
    APP_BG, PANEL_BG, BRAND_RED, BRAND_RED_DARK, TEXT_MAIN, TEXT_SEC,
    TEXT_MUTED, BORDER_COLOR, CARD_HOVER, SUCCESS
)
from rk7_pro.components.icons import VectorIcon


class SettingsPage(QFrame):
    source_changed = pyqtSignal(str)

    def __init__(self, initial_path):
        super().__init__()
        self.setStyleSheet(f"background: {APP_BG}; border: none;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame(self)
        header.setFixedHeight(88)
        header.setStyleSheet(f"background: #FFFFFF; border-bottom: 1px solid {BORDER_COLOR};")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(28, 16, 28, 16)
        header_row.setSpacing(16)

        rail = QFrame(header)
        rail.setFixedSize(4, 32)
        rail.setStyleSheet(f"background: {BRAND_RED}; border-radius: 2px; border: none;")
        header_row.addWidget(rail)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("Settings", header)
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 19px; font-weight: 800; border: none;"
        )
        subtitle = QLabel("Configure where RK7 Pro discovers shortcut files", header)
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        header_row.addLayout(copy)
        header_row.addStretch()
        root.addWidget(header)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        content = QWidget(scroll)
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(28, 28, 28, 28)
        content_layout.setSpacing(16)

        card = QFrame(content)
        card.setMaximumWidth(820)
        card.setObjectName("sourceCard")
        card.setStyleSheet(f"""
            QFrame#sourceCard {{
                background: {PANEL_BG};
                border: 1px solid {BORDER_COLOR};
                border-radius: 16px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(16)

        card_title_row = QHBoxLayout()
        icon_wrap = QFrame(card)
        icon_wrap.setFixedSize(40, 40)
        icon_wrap.setStyleSheet(
            f"background: #FEF2F2; border: 1px solid #FECACA; border-radius: 11px;"
        )
        icon_layout = QVBoxLayout(icon_wrap)
        icon_layout.setContentsMargins(0, 0, 0, 0)
        icon_layout.addWidget(
            VectorIcon("folders", color=BRAND_RED_DARK, size=17, parent=icon_wrap),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        card_title_row.addWidget(icon_wrap)

        card_copy = QVBoxLayout()
        card_copy.setSpacing(2)
        card_title = QLabel("Shortcut source", card)
        card_title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 14px; font-weight: 800; border: none;"
        )
        card_hint = QLabel("The folder containing the .lnk files shown in your library.", card)
        card_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        card_copy.addWidget(card_title)
        card_copy.addWidget(card_hint)
        card_title_row.addLayout(card_copy)
        card_title_row.addStretch()
        card_layout.addLayout(card_title_row)

        divider = QFrame(card)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER_COLOR}; border: none;")
        card_layout.addWidget(divider)

        field_label = QLabel("SOURCE FOLDER", card)
        field_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: 800; letter-spacing: 0.7px; border: none;"
        )
        card_layout.addWidget(field_label)

        field_row = QHBoxLayout()
        field_row.setSpacing(8)
        self.path_input = QLineEdit(str(initial_path), card)
        self.path_input.setFixedHeight(40)
        self.path_input.setStyleSheet(f"""
            QLineEdit {{
                background: #FFFFFF;
                color: {TEXT_MAIN};
                border: 1px solid {BORDER_COLOR};
                border-radius: 10px;
                padding: 0 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1.5px solid {BRAND_RED}; }}
        """)
        self.path_input.returnPressed.connect(self._on_reload)
        field_row.addWidget(self.path_input, stretch=1)

        self.browse_btn = self._make_button("Browse", primary=False)
        self.browse_btn.clicked.connect(self._on_browse)
        field_row.addWidget(self.browse_btn)
        card_layout.addLayout(field_row)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.status_lbl = QLabel("Ready to scan", card)
        self.status_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        actions.addWidget(self.status_lbl)
        actions.addStretch()
        self.reload_btn = self._make_button("Reload list", primary=False)
        self.reload_btn.clicked.connect(self._on_reload)
        actions.addWidget(self.reload_btn)
        self.save_btn = self._make_button("Save default", primary=True)
        self.save_btn.clicked.connect(self._on_save)
        actions.addWidget(self.save_btn)
        card_layout.addLayout(actions)

        content_layout.addWidget(card, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        content_layout.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _make_button(self, text, primary=False):
        button = QPushButton(text, self)
        button.setFixedHeight(38)
        button.setMinimumWidth(104)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        if primary:
            button.setStyleSheet(f"""
                QPushButton {{
                    background: {BRAND_RED};
                    color: #FFFFFF;
                    border: 1px solid {BRAND_RED};
                    border-radius: 10px;
                    padding: 0 14px;
                    font-size: 11px;
                    font-weight: 800;
                }}
                QPushButton:hover {{ background: {BRAND_RED_DARK}; border-color: {BRAND_RED_DARK}; }}
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{
                    background: #FFFFFF;
                    color: {TEXT_SEC};
                    border: 1px solid {BORDER_COLOR};
                    border-radius: 10px;
                    padding: 0 14px;
                    font-size: 11px;
                    font-weight: 700;
                }}
                QPushButton:hover {{ background: {CARD_HOVER}; border-color: #CBD5E1; }}
                QPushButton:focus {{ border-color: {BRAND_RED}; }}
            """)
        return button

    def _on_browse(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select shortcut source", self.path_input.text()
        )
        if path:
            self.path_input.setText(path)

    def _on_reload(self):
        path = self.path_input.text().strip()
        if path:
            self.status_lbl.setText("Scanning folder...")
            self.source_changed.emit(path)

    def _on_save(self):
        self._on_reload()

    def update_status(self, text, is_error=False):
        color = "#DC2626" if is_error else SUCCESS
        self.status_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; font-weight: 700; border: none;"
        )
        self.status_lbl.setText(text)