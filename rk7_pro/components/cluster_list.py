from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QScrollArea, QLabel, QHBoxLayout, QGridLayout, QPushButton
)
from PySide6.QtCore import (
    Qt, Signal as pyqtSignal, QPropertyAnimation, QEasingCurve, QAbstractAnimation
)
from PySide6.QtGui import QPainter
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.components.cluster_card import ClusterCard
from rk7_pro.theme import TEXT_MUTED, BORDER_COLOR, TEXT_MAIN, BRAND_RED
from rk7_pro.components.icons import VectorIcon


class AddClusterBtn(QPushButton):
    """Compatibility placeholder; creation is managed through the source folder."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hide()


class ScrollCanvas(QWidget):
    """Opaque surface that clears every exposed pixel before child cards paint."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().window())


class SmoothScrollArea(QScrollArea):
    """Pixel-based wheel scrolling with a short, interruptible easing curve."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target_value = 0
        self._scroll_animation = QPropertyAnimation(
            self.verticalScrollBar(), b"value", self
        )
        self._scroll_animation.setDuration(85)
        self._scroll_animation.setEasingCurve(QEasingCurve.Type.OutQuad)

    def wheelEvent(self, event):
        pixel_delta = event.pixelDelta().y()
        bar = self.verticalScrollBar()
        if pixel_delta:
            self._scroll_animation.stop()
            bar.setValue(bar.value() - pixel_delta)
            self._target_value = bar.value()
            event.accept()
            return

        steps = event.angleDelta().y() / 120.0
        if not steps:
            super().wheelEvent(event)
            return
        base = (
            self._target_value
            if self._scroll_animation.state() == QAbstractAnimation.State.Running
            else bar.value()
        )
        self._target_value = max(
            bar.minimum(), min(bar.maximum(), round(base - steps * 190))
        )
        self._scroll_animation.stop()
        self._scroll_animation.setStartValue(bar.value())
        self._scroll_animation.setEndValue(self._target_value)
        self._scroll_animation.start()
        event.accept()


class ClusterListPanel(QWidget):
    cluster_selected = pyqtSignal(str)
    pin_toggled = pyqtSignal(str, bool)
    go_clicked = pyqtSignal(str)
    customization_requested = pyqtSignal(str)
    ini_clicked = pyqtSignal(str)
    folder_clicked = pyqtSignal(str)

    def __init__(self, mode="launch"):
        super().__init__()
        self.mode = mode
        self.columns = 3
        self.cards = []
        self.selected_idx = -1
        self._filter_text = ""
        self._status_filter = "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setContentsMargins(2, 0, 10, 0)
        header.setSpacing(10)

        rail = QWidget(self)
        rail.setFixedSize(4, 20)
        rail.setStyleSheet(f"background: {BRAND_RED}; border-radius: 2px; border: none;")
        header.addWidget(rail, alignment=Qt.AlignmentFlag.AlignVCenter)

        copy = QVBoxLayout()
        copy.setSpacing(0)
        self.section_lbl = QLabel("SHORTCUT LIBRARY", self)
        self.section_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 12px; font-weight: 800; "
            "letter-spacing: 0.7px; border: none; background: transparent;"
        )
        self.section_hint = QLabel("Click a card to launch", self)
        self.section_hint.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; border: none; background: transparent;"
        )
        copy.addWidget(self.section_lbl)
        copy.addWidget(self.section_hint)
        header.addLayout(copy)
        header.addStretch()

        self.count_lbl = QLabel("0 ITEMS", self)
        self.count_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; "
            f"background: #FFFFFF; border: 1px solid {BORDER_COLOR}; border-radius: 8px; padding: 5px 9px;"
        )
        header.addWidget(self.count_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addLayout(header)

        self.scroll = SmoothScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.scroll.viewport().setStyleSheet("background: #F4F7FB; border: none;")

        self.content_widget = ScrollCanvas(self.scroll)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 10, 20)
        self.content_layout.setSpacing(16)

        self.grid_widget = QWidget(self.content_widget)
        self.grid_widget.setStyleSheet("background: transparent;")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setContentsMargins(0, 0, 0, 0)
        self.grid_layout.setHorizontalSpacing(14)
        self.grid_layout.setVerticalSpacing(14)
        self.content_layout.addWidget(self.grid_widget)

        self.empty_state = QWidget(self.content_widget)
        empty_layout = QVBoxLayout(self.empty_state)
        empty_layout.setContentsMargins(0, 60, 0, 60)
        empty_layout.setSpacing(10)
        empty_icon_wrap = QWidget(self.empty_state)
        empty_icon_wrap.setFixedSize(44, 44)
        empty_icon_wrap.setStyleSheet(
            f"background: #FFFFFF; border: 1px solid {BORDER_COLOR}; border-radius: 12px;"
        )
        empty_icon_layout = QVBoxLayout(empty_icon_wrap)
        empty_icon_layout.setContentsMargins(0, 0, 0, 0)
        empty_icon_layout.addWidget(
            VectorIcon("search", color=TEXT_MUTED, size=18, parent=empty_icon_wrap),
            alignment=Qt.AlignmentFlag.AlignCenter,
        )
        self.empty_label = QLabel("No shortcuts found", self.empty_state)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 700; border: none;"
        )
        empty_hint = QLabel("Try another name or check the source folder in Settings.", self.empty_state)
        empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        empty_layout.addWidget(empty_icon_wrap, alignment=Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(self.empty_label)
        empty_layout.addWidget(empty_hint)
        self.empty_state.hide()
        self.content_layout.addWidget(self.empty_state)
        self.content_layout.addStretch()

        self.add_btn = AddClusterBtn(self.content_widget)
        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll)

    def set_mode(self, mode):
        self.mode = mode
        is_launch = mode == "launch"
        self.section_lbl.setText("SHORTCUT LIBRARY" if is_launch else "FOLDER LIBRARY")
        self.section_hint.setText("Click a card to launch" if is_launch else "Click a card to open its folder")
        for card in self.cards:
            card.mode = mode
            card._update_visuals()

    def set_columns(self, count):
        count = max(1, count)
        if self.columns != count:
            self.columns = count
            self._reflow_cards()

    def set_status_filter(self, filter_name):
        self._status_filter = filter_name if filter_name in {"all", "pinned", "running"} else "all"
        self.filter_cards(self._filter_text)

    def clear(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.cards.clear()
        self.count_lbl.setText("0 ITEMS")

    def populate(self, states):
        self.setUpdatesEnabled(False)
        try:
            self.clear()
            self._filter_text = ""
            for state in states:
                subtitle = state.working_directory or state.target_exe_path or "Path unavailable"
                card = ClusterCard(
                    state.name, subtitle, state.is_pinned, state.is_running,
                    self.mode, custom_name=state.custom_name, custom_color=state.custom_color,
                    custom_icon=state.custom_icon, custom_background=state.custom_background
                )
                card.state_id = state.id
                card.clicked.connect(lambda sid=state.id: self._on_card_click(sid))
                card.double_clicked.connect(lambda sid=state.id: self.go_clicked.emit(sid))
                card.pin_toggled.connect(lambda pinned, sid=state.id: self.pin_toggled.emit(sid, pinned))
                card.go_clicked.connect(lambda sid=state.id: self.go_clicked.emit(sid))
                card.customization_requested.connect(self.customization_requested.emit)
                card.ini_clicked.connect(lambda sid=state.id: self.ini_clicked.emit(sid))
                card.folder_clicked.connect(lambda sid=state.id: self.folder_clicked.emit(sid))
                self.cards.append(card)
            self._reflow_cards()
            self.empty_state.setVisible(not self.cards)
            self.count_lbl.setText(f"{len(self.cards)} ITEMS")
        finally:
            self.setUpdatesEnabled(True)

    def _reflow_cards(self, cards=None):
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
        # New widgets have no parent before their first layout pass and Qt
        # reports them as hidden. Use query state instead of isVisible().
        visible_cards = cards if cards is not None else [
            card for card in self.cards if self._matches_filter(card, self._filter_text)
        ]
        for index, card in enumerate(visible_cards):
            row, column = divmod(index, self.columns)
            # A parentless QWidget becomes a top-level window when shown. Add
            # the card to the grid first so Qt reparents it before it is made
            # visible; otherwise every refresh can flash orphan windows.
            self.grid_layout.addWidget(card, row, column)
            card.setVisible(True)
            self.grid_layout.setColumnStretch(column, 1)

    def _matches_filter(self, card, query):
        text_matches = (
            not query
            or query in card.name.lower()
            or query in card._full_subtitle.lower()
        )
        if self._status_filter == "pinned":
            status_matches = card.is_pinned
        elif self._status_filter == "running":
            status_matches = card.is_active
        else:
            status_matches = True
        return text_matches and status_matches

    def select_card(self, state_id):
        for card in self.cards:
            card.set_selected(card.state_id == state_id)

    def filter_cards(self, text):
        query = text.strip().lower()
        self._filter_text = query
        visible_cards = []
        for card in self.cards:
            visible = self._matches_filter(card, query)
            card.setVisible(visible)
            if visible:
                visible_cards.append(card)
        self._reflow_cards(visible_cards)
        self.empty_state.setVisible(not visible_cards)
        is_filtered = bool(query) or self._status_filter != "all"
        self.count_lbl.setText(
            f"{len(visible_cards)} OF {len(self.cards)} ITEMS"
            if is_filtered else f"{len(self.cards)} ITEMS"
        )

    def _on_card_click(self, state_id):
        self.select_card(state_id)
        self.cluster_selected.emit(state_id)

    def update_state(self, state):
        for card in self.cards:
            if card.state_id == state.id:
                subtitle = state.working_directory or state.target_exe_path or "Path unavailable"
                card.update_info(
                    subtitle, state.is_pinned, state.is_running,
                    custom_name=state.custom_name, custom_color=state.custom_color,
                    custom_icon=state.custom_icon, custom_background=state.custom_background
                )
                break
