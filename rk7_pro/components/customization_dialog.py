from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QFrame, QColorDialog, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import (
    PANEL_BG, BRAND_RED, BRAND_RED_DARK, TEXT_MAIN, TEXT_SEC, TEXT_MUTED,
    BORDER_COLOR, CARD_HOVER
)
from rk7_pro.components.icons import VectorIcon
from rk7_pro.components.phosphor_picker import PhosphorPickerDialog
from rk7_pro.theme_manager import theme_color


class ColorPresetBtn(QPushButton):
    def __init__(self, color_hex, is_selected=False, parent=None):
        super().__init__(parent)
        self.color_hex = color_hex
        self.is_selected = is_selected
        self.setFixedSize(34, 34)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._update_style()

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_style()

    def _update_style(self):
        outer = theme_color(TEXT_MAIN) if self.is_selected else theme_color(BORDER_COLOR)
        width = 3 if self.is_selected else 1
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self.color_hex};
                border: {width}px solid {outer};
                border-radius: 11px;
            }}
            QPushButton:hover {{ border-color: {TEXT_MAIN}; }}
        """)


class IconPresetBtn(QPushButton):
    def __init__(self, icon_key, label, is_selected=False, parent=None):
        super().__init__(parent)
        self.icon_key = icon_key
        self.is_selected = is_selected
        self.setFixedSize(42, 42)
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        if icon_key:
            self.icon_widget = VectorIcon(icon_key, color=TEXT_SEC, size=21, parent=self)
            row.addWidget(self.icon_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            self.icon_widget = None
            initials = QLabel("AB", self)
            initials.setAlignment(Qt.AlignmentFlag.AlignCenter)
            initials.setStyleSheet(
                f"color: {TEXT_SEC}; font-size: 11px; font-weight: 900; "
                "background: transparent; border: none;"
            )
            row.addWidget(initials)
        self._update_style()

    def set_selected(self, selected):
        self.is_selected = selected
        self._update_style()

    def _update_style(self):
        background = theme_color("#FEF2F2" if self.is_selected else "#FFFFFF")
        border = BRAND_RED if self.is_selected else theme_color(BORDER_COLOR)
        self.setStyleSheet(f"""
            QPushButton {{
                background: {background};
                border: {2 if self.is_selected else 1}px solid {border};
                border-radius: 12px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: #CBD5E1; }}
            QPushButton:focus {{ border-color: {BRAND_RED}; }}
        """)
        if self.icon_widget:
            self.icon_widget.set_color(BRAND_RED if self.is_selected else TEXT_SEC)


class CustomizationDialog(QDialog):
    ICON_OPTIONS = [
        (None, "Initials"),
        ("storefront", "Store"),
        ("coffee", "Coffee"),
        ("restaurant", "Restaurant"),
        ("bridge", "Bridge"),
        ("building", "Office"),
        ("monitor", "Computer"),
        ("server", "Server"),
        ("globe", "Website"),
    ]

    def __init__(self, current_name, current_color, current_icon=None, current_background=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Customize shortcut")
        self.setFixedSize(520, 680)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"background: {PANEL_BG}; color: {TEXT_MAIN};")
        self.selected_color = current_color or "#0D9488"
        self.selected_icon = current_icon
        self.selected_background = current_background

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(18)

        header = QHBoxLayout()
        rail = QFrame(self)
        rail.setFixedSize(4, 30)
        rail.setStyleSheet(f"background: {BRAND_RED}; border-radius: 2px; border: none;")
        header.addWidget(rail)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        title = QLabel("Customize shortcut", self)
        title.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 16px; font-weight: 800; border: none;"
        )
        hint = QLabel("Choose a name, icon, identity color and card background.", self)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        copy.addWidget(title)
        copy.addWidget(hint)
        header.addLayout(copy)
        header.addStretch()
        layout.addLayout(header)

        divider = QFrame(self)
        divider.setFixedHeight(1)
        divider.setStyleSheet(f"background: {BORDER_COLOR}; border: none;")
        layout.addWidget(divider)

        name_group = QVBoxLayout()
        name_group.setSpacing(7)
        name_label = QLabel("DISPLAY NAME", self)
        name_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: 800; letter-spacing: 0.7px;"
        )
        self.name_input = QLineEdit(current_name or "", self)
        self.name_input.setFixedHeight(40)
        self.name_input.setPlaceholderText("Keep empty to use the original name")
        self.name_input.setStyleSheet(f"""
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
        name_group.addWidget(name_label)
        name_group.addWidget(self.name_input)
        layout.addLayout(name_group)

        icon_group = QVBoxLayout()
        icon_group.setSpacing(8)
        icon_label = QLabel("IDENTITY ICON", self)
        icon_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: 800; letter-spacing: 0.7px;"
        )
        icon_group.addWidget(icon_label)
        icon_grid = QGridLayout()
        icon_grid.setContentsMargins(0, 0, 0, 0)
        icon_grid.setHorizontalSpacing(8)
        icon_grid.setVerticalSpacing(8)
        self.icon_btns = []
        for index, (icon_key, label) in enumerate(self.ICON_OPTIONS):
            button = IconPresetBtn(icon_key, label, self.selected_icon == icon_key, self)
            button.clicked.connect(
                lambda checked=False, value=icon_key: self._select_icon(value)
            )
            icon_grid.addWidget(button, index // 6, index % 6)
            self.icon_btns.append(button)
        icon_grid.setColumnStretch(6, 1)
        icon_group.addLayout(icon_grid)
        phosphor_row = QHBoxLayout()
        phosphor_row.setSpacing(8)
        self.browse_phosphor_btn = self._make_action("Browse Phosphor library", primary=False)
        self.browse_phosphor_btn.setMinimumWidth(168)
        self.browse_phosphor_btn.clicked.connect(self._browse_phosphor)
        phosphor_row.addWidget(self.browse_phosphor_btn)
        self.phosphor_selection_lbl = QLabel(self)
        self.phosphor_selection_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 600; border: none;"
        )
        phosphor_row.addWidget(self.phosphor_selection_lbl)
        phosphor_row.addStretch()
        icon_group.addLayout(phosphor_row)
        layout.addLayout(icon_group)
        self._update_phosphor_selection_label()

        background_group = QVBoxLayout()
        background_group.setSpacing(8)
        background_label = QLabel("CARD BACKGROUND", self)
        background_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: 800; letter-spacing: 0.7px;"
        )
        background_group.addWidget(background_label)
        self.background_preview = QLabel(self)
        self.background_preview.setFixedHeight(92)
        self.background_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.background_preview.setStyleSheet(
            f"background: {theme_color('#0C111D')}; color: {TEXT_MUTED}; "
            f"border: 1px solid {BORDER_COLOR}; border-radius: 12px; font-size: 11px;"
        )
        background_group.addWidget(self.background_preview)
        background_actions = QHBoxLayout()
        background_actions.setSpacing(8)
        self.choose_background_btn = self._make_action("Choose image", primary=False)
        self.choose_background_btn.clicked.connect(self._pick_background)
        background_actions.addWidget(self.choose_background_btn)
        self.remove_background_btn = self._make_action("Remove", primary=False)
        self.remove_background_btn.clicked.connect(self._clear_background)
        background_actions.addWidget(self.remove_background_btn)
        background_hint = QLabel("PNG/WebP 512×512 for logos · 1600×900 for photos", self)
        background_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 9px; border: none;")
        background_actions.addWidget(background_hint)
        background_actions.addStretch()
        background_group.addLayout(background_actions)
        layout.addLayout(background_group)
        self._update_background_preview()

        color_group = QVBoxLayout()
        color_group.setSpacing(8)
        color_label = QLabel("IDENTITY COLOR", self)
        color_label.setStyleSheet(
            f"color: {TEXT_SEC}; font-size: 10px; font-weight: 800; letter-spacing: 0.7px;"
        )
        color_group.addWidget(color_label)
        color_row = QHBoxLayout()
        color_row.setSpacing(8)
        presets = ["#0D9488", "#2563EB", "#7C3AED", "#D97706", "#059669", "#475569", "#DC2626"]
        self.preset_btns = []
        for color in presets:
            button = ColorPresetBtn(
                color, self.selected_color.upper() == color.upper(), self
            )
            button.clicked.connect(lambda checked=False, value=color: self._select_color(value))
            color_row.addWidget(button)
            self.preset_btns.append(button)

        self.custom_btn = self._make_action("Custom", primary=False)
        self.custom_btn.setMinimumWidth(74)
        self.custom_btn.clicked.connect(self._pick_custom_color)
        color_row.addWidget(self.custom_btn)
        color_row.addStretch()
        color_group.addLayout(color_row)
        layout.addLayout(color_group)
        layout.addStretch()

        actions = QHBoxLayout()
        actions.addStretch()
        self.cancel_btn = self._make_action("Cancel", primary=False)
        self.cancel_btn.clicked.connect(self.reject)
        actions.addWidget(self.cancel_btn)
        self.save_btn = self._make_action("Save changes", primary=True)
        self.save_btn.setMinimumWidth(116)
        self.save_btn.clicked.connect(self.accept)
        actions.addWidget(self.save_btn)
        layout.addLayout(actions)

    def _make_action(self, text, primary=False):
        button = QPushButton(text, self)
        button.setFixedHeight(38)
        button.setMinimumWidth(86)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        if primary:
            button.setStyleSheet(f"""
                QPushButton {{
                    background: {BRAND_RED};
                    color: white;
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

    def _select_color(self, color_hex):
        self.selected_color = color_hex
        for button in self.preset_btns:
            button.set_selected(button.color_hex.upper() == color_hex.upper())

    def _select_icon(self, icon_key):
        self.selected_icon = icon_key
        for button in self.icon_btns:
            button.set_selected(button.icon_key == icon_key)
        self._update_phosphor_selection_label()

    def _browse_phosphor(self):
        picker = PhosphorPickerDialog(self.selected_icon, self)
        if picker.exec():
            selected = picker.get_icon()
            if selected:
                self._select_icon(selected)

    def _update_phosphor_selection_label(self):
        if self.selected_icon and self.selected_icon.startswith("phosphor:"):
            parts = self.selected_icon.split(":", 2)
            label = parts[2].replace("-", " ").title() if len(parts) == 3 else self.selected_icon
            self.phosphor_selection_lbl.setText(label)
            self.phosphor_selection_lbl.setToolTip(self.selected_icon)
        else:
            self.phosphor_selection_lbl.setText("1,512 icons · 6 weights")
            self.phosphor_selection_lbl.setToolTip("")

    def _pick_custom_color(self):
        color = QColorDialog.getColor(QColor(self.selected_color), self, "Select color")
        if color.isValid():
            self._select_color(color.name())

    def _pick_background(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose card background",
            self.selected_background or "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        if path:
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self.selected_background = path
                self._update_background_preview()

    def _clear_background(self):
        self.selected_background = None
        self._update_background_preview()

    def _update_background_preview(self):
        if self.selected_background and os.path.isfile(self.selected_background):
            pixmap = QPixmap(self.selected_background)
            if not pixmap.isNull():
                preview = pixmap.scaled(
                    max(1, self.background_preview.width() - 8),
                    max(1, self.background_preview.height() - 8),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.background_preview.setText("")
                self.background_preview.setPixmap(preview)
                self.remove_background_btn.setEnabled(True)
                self.background_preview.setToolTip(self.selected_background)
                return
        self.background_preview.clear()
        self.background_preview.setText("No background image selected")
        self.background_preview.setToolTip("")
        self.remove_background_btn.setEnabled(False)

    def get_values(self):
        return (
            self.name_input.text().strip(),
            self.selected_color,
            self.selected_icon,
            self.selected_background,
        )