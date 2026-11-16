from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget
)

from rk7_pro.components.icons import VectorIcon
from rk7_pro.components.phosphor_icons import (
    PHOSPHOR_WEIGHTS, available_phosphor_names, make_phosphor_key,
    parse_phosphor_key,
)
from rk7_pro.theme import (
    BRAND_RED, BRAND_RED_DARK, BORDER_COLOR, CARD_HOVER, PANEL_BG,
    TEXT_MAIN, TEXT_MUTED, TEXT_SEC,
)
from rk7_pro.theme_manager import apply_widget_theme, is_dark_mode, theme_color


class PhosphorChoiceButton(QPushButton):
    def __init__(self, name, weight, parent=None):
        super().__init__(parent)
        self.icon_name = name
        self.weight = weight
        self.icon_key = make_phosphor_key(name, weight)
        self.selected = False
        self.setFixedSize(58, 58)
        self.setToolTip(name.replace("-", " ").title())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.icon = VectorIcon(self.icon_key, color=TEXT_SEC, size=24, parent=self)
        layout.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self._update_style()

    def set_selected(self, selected):
        self.selected = bool(selected)
        self._update_style()

    def _update_style(self):
        background = theme_color("#EFF6FF" if self.selected else "#FFFFFF")
        border = "#2684FF" if self.selected else theme_color(BORDER_COLOR)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {background};
                border: {2 if self.selected else 1}px solid {border};
                border-radius: 11px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: #93C5FD; }}
            QPushButton:focus {{ border-color: #2684FF; }}
        """)
        self.icon.set_color("#0052CC" if self.selected else TEXT_SEC)


class PhosphorPickerDialog(QDialog):
    RESULT_LIMIT = 160

    def __init__(self, current_icon=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose Phosphor icon")
        self.setFixedSize(760, 620)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"background: {PANEL_BG}; color: {TEXT_MAIN};")
        self.selected_icon = None
        self._buttons = []

        parsed = parse_phosphor_key(current_icon)
        initial_weight, initial_name = parsed if parsed else ("light", "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(16)

        header = QHBoxLayout()
        rail = QFrame(self)
        rail.setFixedSize(4, 30)
        rail.setStyleSheet(f"background: {BRAND_RED}; border: none; border-radius: 2px;")
        header.addWidget(rail)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel("Phosphor icon library", self)
        title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 800; border: none;")
        subtitle = QLabel("Search 1,512 icons and choose a visual weight.", self)
        subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        copy.addWidget(title)
        copy.addWidget(subtitle)
        header.addLayout(copy)
        header.addStretch()
        layout.addLayout(header)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.search_input = QLineEdit(self)
        self.search_input.setFixedHeight(40)
        self.search_input.setPlaceholderText("Search icons, e.g. coffee, store, monitor...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: #FFFFFF; color: {TEXT_MAIN}; border: 1px solid {BORDER_COLOR};
                border-radius: 10px; padding: 0 12px; font-size: 12px;
            }}
            QLineEdit:focus {{ border: 1.5px solid #2684FF; }}
        """)
        toolbar.addWidget(self.search_input, stretch=1)
        self.weight_combo = QComboBox(self)
        self.weight_combo.setFixedSize(126, 40)
        for weight in PHOSPHOR_WEIGHTS:
            self.weight_combo.addItem(weight.upper(), weight)
        self.weight_combo.setCurrentIndex(PHOSPHOR_WEIGHTS.index(initial_weight))
        self.weight_combo.setStyleSheet(f"""
            QComboBox {{
                background: #FFFFFF; color: {TEXT_MAIN}; border: 1px solid {BORDER_COLOR};
                border-radius: 10px; padding: 0 10px; font-size: 11px; font-weight: 800;
            }}
            QComboBox:focus {{ border-color: #2684FF; }}
        """)
        toolbar.addWidget(self.weight_combo)
        layout.addLayout(toolbar)

        self.result_label = QLabel(self)
        self.result_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; border: none;")
        layout.addWidget(self.result_label)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.grid_host = QWidget(self.scroll)
        self.grid_host.setStyleSheet("background: transparent; border: none;")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 8, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(8)
        self.scroll.setWidget(self.grid_host)
        layout.addWidget(self.scroll, stretch=1)

        footer = QHBoxLayout()
        self.selected_label = QLabel("No icon selected", self)
        self.selected_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: 700; border: none;")
        footer.addWidget(self.selected_label)
        footer.addStretch()
        cancel = self._make_action("Cancel", False)
        cancel.clicked.connect(self.reject)
        footer.addWidget(cancel)
        self.use_btn = self._make_action("Use icon", True)
        self.use_btn.setEnabled(False)
        self.use_btn.clicked.connect(self.accept)
        footer.addWidget(self.use_btn)
        layout.addLayout(footer)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(120)
        self._refresh_timer.timeout.connect(self._refresh_grid)
        self.search_input.textChanged.connect(lambda _text: self._refresh_timer.start())
        self.weight_combo.currentIndexChanged.connect(lambda _index: self._refresh_grid())
        if initial_name:
            self.search_input.setText(initial_name)
        self._refresh_grid()
        apply_widget_theme(self, is_dark_mode())

    def _make_action(self, text, primary):
        button = QPushButton(text, self)
        button.setFixedHeight(38)
        button.setMinimumWidth(92)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setStyleSheet(f"""
                QPushButton {{ background: {BRAND_RED}; color: white; border: 1px solid {BRAND_RED};
                    border-radius: 10px; padding: 0 14px; font-size: 11px; font-weight: 800; }}
                QPushButton:hover {{ background: {BRAND_RED_DARK}; border-color: {BRAND_RED_DARK}; }}
                QPushButton:disabled {{ background: #CBD5E1; border-color: #CBD5E1; }}
            """)
        else:
            button.setStyleSheet(f"""
                QPushButton {{ background: #FFFFFF; color: {TEXT_SEC}; border: 1px solid {BORDER_COLOR};
                    border-radius: 10px; padding: 0 14px; font-size: 11px; font-weight: 700; }}
                QPushButton:hover {{ background: {CARD_HOVER}; }}
            """)
        return button

    def _clear_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._buttons.clear()

    def _refresh_grid(self):
        self._clear_grid()
        weight = self.weight_combo.currentData() or "regular"
        names = available_phosphor_names(weight)
        query = self.search_input.text().strip().lower().replace("_", "-").replace(" ", "-")
        matches = [name for name in names if query in name] if query else list(names)
        visible = matches[:self.RESULT_LIMIT]
        columns = 10
        for index, name in enumerate(visible):
            button = PhosphorChoiceButton(name, weight, self.grid_host)
            button.clicked.connect(lambda checked=False, value=button.icon_key: self._select(value))
            self.grid.addWidget(button, index // columns, index % columns)
            self._buttons.append(button)
        for column in range(columns):
            self.grid.setColumnStretch(column, 1)
        suffix = f" · showing first {len(visible)}" if len(matches) > len(visible) else ""
        self.result_label.setText(f"{len(matches)} matches{suffix}")
        self.grid_host.adjustSize()

    def _select(self, icon_key):
        self.selected_icon = icon_key
        for button in self._buttons:
            button.set_selected(button.icon_key == icon_key)
        parsed = parse_phosphor_key(icon_key)
        label = parsed[1].replace("-", " ").title() if parsed else icon_key
        self.selected_label.setText(f"Selected: {label}")
        self.use_btn.setEnabled(True)

    def get_icon(self):
        return self.selected_icon