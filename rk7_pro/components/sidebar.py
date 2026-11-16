# rk7_pro/components/sidebar.py
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
)
from PySide6.QtCore import Qt, Signal as pyqtSignal
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import BRAND_RED, TEXT_MAIN, TEXT_SEC, TEXT_MUTED
from rk7_pro.components.icons import VectorIcon


class AivoraNavButton(QPushButton):
    def __init__(self, icon_name, text, badge_count=None, is_active=False, is_compact=False, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.label_text = text
        self.badge_count = badge_count
        self.is_active = is_active
        self.is_compact = is_compact

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(38)

        self.row = QHBoxLayout(self)
        self.row.setContentsMargins(10, 0, 10, 0)
        self.row.setSpacing(10)

        # Icon
        self.icon_widget = VectorIcon(icon_name, size=16, parent=self)
        self.row.addWidget(self.icon_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Label
        self.text_lbl = QLabel(text, self)
        self.row.addWidget(self.text_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.row.addStretch()

        # Dot Indicator (Active status in Aivora style)
        self.dot_indicator = QFrame(self)
        self.dot_indicator.setFixedSize(6, 6)
        self.dot_indicator.setStyleSheet(f"background: {BRAND_RED}; border-radius: 3px; border: none;")
        self.row.addWidget(self.dot_indicator, alignment=Qt.AlignmentFlag.AlignVCenter)

        # Optional Count Badge
        self.badge_lbl = QLabel(str(badge_count) if badge_count is not None else "", self)
        self.badge_lbl.setStyleSheet("""
            QLabel {
                color: #94A3B8;
                background: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 5px;
                padding: 1px 5px;
                font-size: 10px;
                font-weight: 700;
            }
        """)
        self.row.addWidget(self.badge_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        if badge_count is None:
            self.badge_lbl.hide()

        self.update_mode(is_compact)

    def set_active(self, active: bool):
        self.is_active = active
        self._apply_style()

    def set_badge(self, count):
        self.badge_count = count
        if count is not None and count > 0:
            self.badge_lbl.setText(str(count))
            if not self.is_compact:
                self.badge_lbl.show()
        else:
            self.badge_lbl.hide()

    def update_mode(self, is_compact: bool):
        self.is_compact = is_compact
        if self.is_compact:
            self.text_lbl.hide()
            self.dot_indicator.hide()
            self.badge_lbl.hide()
            self.row.setContentsMargins(0, 0, 0, 0)
            self.row.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.setToolTip(self.label_text)
        else:
            self.text_lbl.show()
            self.row.setContentsMargins(10, 0, 10, 0)
            self.row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.setToolTip("")
            if self.is_active:
                self.dot_indicator.show()
            else:
                self.dot_indicator.hide()
            if self.badge_count is not None and self.badge_count > 0:
                self.badge_lbl.show()
        self._apply_style()

    def _apply_style(self):
        if self.is_active:
            bg = "#1E232D"
            text_color = "#FFFFFF"
            icon_color = "#3B82F6"
            font_weight = "700"
            if not self.is_compact:
                self.dot_indicator.show()
        else:
            bg = "transparent"
            text_color = "#94A3B8"
            icon_color = "#64748B"
            font_weight = "500"
            self.dot_indicator.hide()

        self.icon_widget.set_color(icon_color)
        self.text_lbl.setStyleSheet(
            f"color: {text_color}; font-size: 13px; font-weight: {font_weight}; background: transparent; border: none;"
        )
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: none;
                border-radius: 8px;
            }}
            QPushButton:hover {{
                background-color: {'#252C38' if self.is_active else '#181C24'};
            }}
        """)


class SidebarNavigation(QWidget):
    module_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("_rk7_theme_static", True)
        self.is_collapsed = False
        self.expanded_width = 240
        self.collapsed_width = 72

        self.setFixedWidth(self.expanded_width)
        self.setStyleSheet("background: transparent;")

        # Outer layout creates floating container padding
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 12, 6, 12)
        outer_layout.setSpacing(0)

        # Floating Card Container (Shadcn Dark Style Card)
        self.card = QFrame(self)
        self.card.setStyleSheet("""
            QFrame#aivoraCard {
                background-color: #0D0F12;
                border: 1px solid #1E232D;
                border-radius: 16px;
            }
        """)
        self.card.setObjectName("aivoraCard")
        outer_layout.addWidget(self.card)

        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(12, 16, 12, 14)
        layout.setSpacing(5)

        # 1. Header: Brand Logo + App Name + Collapse Toggle (⇥ icon)
        self.header_widget = QWidget(self.card)
        self.header_widget.setFixedHeight(40)
        self.header_layout = QHBoxLayout(self.header_widget)
        self.header_layout.setContentsMargins(4, 0, 4, 0)
        self.header_layout.setSpacing(8)

        # Brand Icon Badge
        self.brand_mark = QFrame(self.header_widget)
        self.brand_mark.setFixedSize(32, 32)
        self.brand_mark.setStyleSheet(f"background: {BRAND_RED}; border-radius: 9px; border: none;")
        bm_l = QVBoxLayout(self.brand_mark)
        bm_l.setContentsMargins(0, 0, 0, 0)
        self.mark_label = QLabel("R7", self.brand_mark)
        self.mark_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mark_label.setStyleSheet("color: white; font-size: 13px; font-weight: 900; border: none;")
        bm_l.addWidget(self.mark_label)
        self.header_layout.addWidget(self.brand_mark)

        # Brand Name
        self.brand_text_box = QWidget(self.header_widget)
        self.brand_text_box.setStyleSheet("background: transparent; border: none;")
        bt_l = QVBoxLayout(self.brand_text_box)
        bt_l.setContentsMargins(0, 0, 0, 0)
        bt_l.setSpacing(0)
        self.brand_title = QLabel("RK7 PRO", self.brand_text_box)
        self.brand_title.setStyleSheet("color: #F8FAFC; font-size: 14px; font-weight: 800; border: none;")
        self.brand_sub = QLabel("Control Center", self.brand_text_box)
        self.brand_sub.setStyleSheet("color: #64748B; font-size: 9px; font-weight: 700; border: none;")
        bt_l.addWidget(self.brand_title)
        bt_l.addWidget(self.brand_sub)
        self.header_layout.addWidget(self.brand_text_box, stretch=1)

        # Collapse Button
        self.btn_toggle = QPushButton(self.header_widget)
        self.btn_toggle.setFixedSize(28, 28)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setToolTip("Thu gọn Sidebar")
        self.btn_toggle.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover {
                background: #181C24;
            }
        """)
        bt_l = QVBoxLayout(self.btn_toggle)
        bt_l.setContentsMargins(0, 0, 0, 0)
        self.toggle_icon = VectorIcon("arrow_left", color="#64748B", size=14, parent=self.btn_toggle)
        bt_l.addWidget(self.toggle_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self.btn_toggle.clicked.connect(self.toggle_collapse)
        self.header_layout.addWidget(self.btn_toggle)

        layout.addWidget(self.header_widget)
        layout.addSpacing(6)

        # 2. Quick Action / Search Button (Shadcn style with ⌘K / Ctrl K badge)
        self.btn_quick_search = QPushButton(self.card)
        self.btn_quick_search.setFixedHeight(34)
        self.btn_quick_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_quick_search.setStyleSheet("""
            QPushButton {
                background: #13161C;
                border: 1px solid #1E232D;
                border-radius: 8px;
                padding: 0 8px;
            }
            QPushButton:hover {
                background: #181C24;
                border-color: #2D3748;
            }
        """)
        qs_row = QHBoxLayout(self.btn_quick_search)
        qs_row.setContentsMargins(8, 0, 8, 0)
        qs_row.setSpacing(8)
        self.qs_icon = VectorIcon("search", color="#64748B", size=14, parent=self.btn_quick_search)
        qs_row.addWidget(self.qs_icon)
        self.qs_text = QLabel("Tìm kiếm...", self.btn_quick_search)
        self.qs_text.setStyleSheet("color: #64748B; font-size: 11px; font-weight: 500; border: none; background: transparent;")
        qs_row.addWidget(self.qs_text)
        qs_row.addStretch()
        self.qs_badge = QLabel("Ctrl K", self.btn_quick_search)
        self.qs_badge.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 700; background: #1E232D; border: 1px solid #2B3240; border-radius: 4px; padding: 1px 4px;")
        qs_row.addWidget(self.qs_badge)
        layout.addWidget(self.btn_quick_search)

        layout.addSpacing(10)

        # 3. MAIN MENU Heading
        self.menu_heading = QLabel("DASHBOARDS", self.card)
        self.menu_heading.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; padding-left: 8px; border: none;")
        layout.addWidget(self.menu_heading)

        # 4. Main Nav Items
        self.nav_items = {}
        nav_defs = [
            ("launch", "LAUNCH", None),
            ("database", "SCRIPT VAULT", None),
            ("bell", "GHI ISSUE", None),
        ]

        for index, (icon_name, text, badge) in enumerate(nav_defs):
            btn = AivoraNavButton(icon_name, text, badge_count=badge, is_active=(index == 0), parent=self.card)
            btn.clicked.connect(lambda checked=False, name=text: self._on_nav_click(name))
            self.nav_items[text] = btn
            layout.addWidget(btn)

        layout.addSpacing(10)

        # 5. SYSTEM Heading & Settings
        self.system_heading = QLabel("SYSTEM", self.card)
        self.system_heading.setStyleSheet("color: #64748B; font-size: 10px; font-weight: 800; letter-spacing: 0.8px; padding-left: 8px; border: none;")
        layout.addWidget(self.system_heading)

        btn_settings = AivoraNavButton("settings", "SETTINGS", parent=self.card)
        btn_settings.clicked.connect(lambda: self._on_nav_click("SETTINGS"))
        self.nav_items["SETTINGS"] = btn_settings
        layout.addWidget(btn_settings)

        layout.addStretch()

        # 6. User Profile Card at Footer (Shadcn Dark Profile)
        self.footer_profile = QFrame(self.card)
        self.footer_profile.setFixedHeight(48)
        self.footer_profile.setStyleSheet("""
            QFrame {
                background: #13161C;
                border: 1px solid #1E232D;
                border-radius: 10px;
            }
        """)
        fp_layout = QHBoxLayout(self.footer_profile)
        fp_layout.setContentsMargins(8, 6, 8, 6)
        fp_layout.setSpacing(8)

        # Avatar
        self.avatar_circle = QFrame(self.footer_profile)
        self.avatar_circle.setFixedSize(28, 28)
        self.avatar_circle.setStyleSheet(f"background: {BRAND_RED}; border-radius: 14px; border: none;")
        av_l = QVBoxLayout(self.avatar_circle)
        av_l.setContentsMargins(0, 0, 0, 0)
        av_t = QLabel("AD", self.avatar_circle)
        av_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        av_t.setStyleSheet("color: white; font-size: 10px; font-weight: 900; border: none;")
        av_l.addWidget(av_t)
        fp_layout.addWidget(self.avatar_circle)

        # Info
        self.profile_info = QWidget(self.footer_profile)
        self.profile_info.setStyleSheet("background: transparent; border: none;")
        pi_l = QVBoxLayout(self.profile_info)
        pi_l.setContentsMargins(0, 0, 0, 0)
        pi_l.setSpacing(0)
        self.user_name = QLabel("Admin User", self.profile_info)
        self.user_name.setStyleSheet("color: #F8FAFC; font-size: 11px; font-weight: 700; border: none;")
        self.user_status = QLabel("System Online", self.profile_info)
        self.user_status.setStyleSheet("color: #10B981; font-size: 9px; font-weight: 700; border: none;")
        pi_l.addWidget(self.user_name)
        pi_l.addWidget(self.user_status)
        fp_layout.addWidget(self.profile_info, stretch=1)

        layout.addWidget(self.footer_profile)

    def toggle_collapse(self):
        self.set_collapsed(not self.is_collapsed)

    def set_collapsed(self, collapsed: bool):
        self.is_collapsed = collapsed
        target_w = self.collapsed_width if self.is_collapsed else self.expanded_width
        self.setFixedWidth(target_w)

        if self.is_collapsed:
            self.brand_text_box.hide()
            self.btn_quick_search.hide()
            self.menu_heading.hide()
            self.system_heading.hide()
            self.profile_info.hide()
            self.btn_toggle.setToolTip("Mở rộng Sidebar")
            self.toggle_icon.set_icon_name("arrow_right")
            self.header_layout.setContentsMargins(0, 0, 0, 0)
            self.header_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            self.brand_text_box.show()
            self.btn_quick_search.show()
            self.menu_heading.show()
            self.system_heading.show()
            self.profile_info.show()
            self.btn_toggle.setToolTip("Thu gọn Sidebar")
            self.toggle_icon.set_icon_name("arrow_left")
            self.header_layout.setContentsMargins(4, 0, 4, 0)
            self.header_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for btn in self.nav_items.values():
            btn.update_mode(self.is_collapsed)

    def _on_nav_click(self, text):
        for name, button in self.nav_items.items():
            button.set_active(name == text)
        self.module_changed.emit(text)