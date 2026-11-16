from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QGraphicsDropShadowEffect, QWidget
)
from PySide6.QtCore import (
    Qt, Signal as pyqtSignal, Property, QPropertyAnimation,
    QEasingCurve, QRectF, QTimer, QLineF, QEvent
)
from PySide6.QtGui import (
    QColor, QPainter, QPen, QBrush, QPainterPath,
    QLinearGradient, QRadialGradient, QPixmap
)
import hashlib
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import BRAND_RED, SUCCESS
from rk7_pro.theme_manager import is_dark_mode
from rk7_pro.components.icons import VectorIcon


class CardActionButton(QPushButton):
    """Theme-aware icon button shared by every card action."""

    MUTED = "#9CA3AF"
    WHITE = "#F3F4F6"
    BLUE = "#2684FF"

    def __init__(self, icon_name, tooltip, primary=False, parent=None):
        super().__init__(parent)
        self.primary = primary
        self.active = False
        self.icon_name = icon_name.lower()
        self.accent_color = self.BLUE
        self._hover_progress = 0.0
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip(tooltip)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        self.icon = VectorIcon(icon_name, color=self.MUTED, size=22, parent=self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.icon, alignment=Qt.AlignmentFlag.AlignCenter)

        self._hover_animation = QPropertyAnimation(self, b"hoverProgress", self)
        self._hover_animation.setDuration(180)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.set_hover_progress(0.0)

    @staticmethod
    def _mix(start_hex, end_hex, amount):
        start = QColor(start_hex)
        end = QColor(end_hex)
        amount = max(0.0, min(1.0, amount))
        return QColor(
            round(start.red() + (end.red() - start.red()) * amount),
            round(start.green() + (end.green() - start.green()) * amount),
            round(start.blue() + (end.blue() - start.blue()) * amount),
        ).name()

    @staticmethod
    def _theme_colors():
        return ("#94A3B8", "#FFFFFF") if is_dark_mode() else ("#475569", "#142033")

    def get_hover_progress(self):
        return self._hover_progress

    def set_hover_progress(self, value):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        muted, target = self._theme_colors()
        self.icon.set_color(self._mix(muted, target, self._hover_progress))
        self.update()

    hoverProgress = Property(float, get_hover_progress, set_hover_progress)

    def _animate_to(self, target):
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def set_active(self, active):
        self.active = bool(active)
        self.set_hover_progress(self._hover_progress)

    def enterEvent(self, event):
        self._animate_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_to(0.0)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self.update()
        super().focusOutEvent(event)

    def changeEvent(self, event):
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self.set_hover_progress(self._hover_progress)
        super().changeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        alpha = 72 if self.isDown() else round(28 * self._hover_progress)
        painter.setPen(Qt.PenStyle.NoPen)
        hover_color = (
            QColor(255, 255, 255, alpha)
            if is_dark_mode()
            else QColor(20, 32, 51, alpha)
        )
        painter.setBrush(hover_color)
        painter.drawRoundedRect(rect, 8, 8)
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(self.BLUE), 1.5))
            painter.drawRoundedRect(rect, 8, 8)


class FavoriteActionButton(CardActionButton):
    """Favorite button with restrained amber feedback."""

    AMBER = "#FBBF24"

    def __init__(self, parent=None):
        super().__init__("phosphor:regular:bookmark-simple", "Add to favorites", parent=parent)

    def set_hover_progress(self, value):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        muted, _ = self._theme_colors()
        start = self.AMBER if self.active else muted
        self.icon.set_color(self._mix(start, self.AMBER, self._hover_progress))
        self.update()

    hoverProgress = Property(float, CardActionButton.get_hover_progress, set_hover_progress)

    def set_active(self, active):
        self.active = bool(active)
        self.icon.set_icon_name(
            "phosphor:regular:bookmark-simple"
        )
        self.setToolTip("Remove from favorites" if self.active else "Add to favorites")
        self.set_hover_progress(self._hover_progress)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hover_progress > 0 or self.active:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            alpha = round((18 if self.active else 0) + 18 * self._hover_progress)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(251, 191, 36, alpha))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(2, 2, -2, -2), 8, 8)


class ClusterCard(QFrame):
    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    pin_toggled = pyqtSignal(bool)
    go_clicked = pyqtSignal()
    customization_requested = pyqtSignal(str)
    ini_clicked = pyqtSignal()
    folder_clicked = pyqtSignal()

    def __init__(self, name, subtitle, is_pinned=False, is_active=False,
                 mode="launch", custom_name=None, custom_color=None, custom_icon=None,
                 custom_background=None):
        super().__init__()
        self.name = name
        self.mode = mode
        self.is_pinned = is_pinned
        self.is_active = is_active
        self.is_selected = False
        self._full_subtitle = subtitle
        self.custom_name = custom_name
        self.custom_color = custom_color
        self.custom_icon = custom_icon
        self.custom_background = custom_background
        self._background_pixmap = QPixmap()
        self._scaled_background = None
        self._scaled_background_size = None
        self._display_name = custom_name or name
        self._hover_progress = 0.0
        self._grid_offset = 0.0
        self._cursor_visible = True

        self.setFixedHeight(246)
        self.setMinimumWidth(280)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setProperty("_rk7_theme_static", True)
        self.setStyleSheet("ClusterCard { background: transparent; border: none; }")

        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(18)
        self.shadow.setColor(QColor(0, 0, 0, 52))
        self.shadow.setOffset(0, 4)
        # Compatibility handle only: attaching 74 offscreen blur effects makes scrolling expensive.

        self._hover_animation = QPropertyAnimation(self, b"cardHoverProgress", self)
        self._hover_animation.setDuration(260)
        self._hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._grid_animation = QPropertyAnimation(self, b"gridOffset", self)
        self._grid_animation.setStartValue(0.0)
        self._grid_animation.setEndValue(30.0)
        self._grid_animation.setDuration(20000)
        self._grid_animation.setLoopCount(-1)
        self._grid_animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setInterval(500)
        self._cursor_timer.timeout.connect(self._toggle_cursor)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 16)
        root.setSpacing(0)

        # Artwork zone: uploaded images are drawn only behind this area.
        self.top_content = QWidget(self)
        self.top_content.setFixedHeight(104)
        self.top_content.setStyleSheet("background: transparent; border: none;")
        top_layout = QVBoxLayout(self.top_content)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(2)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        self.folder_btn = CardActionButton("phosphor:regular:folder-open", "Open folder", parent=self)
        self.ini_btn = CardActionButton("phosphor:regular:file-text", "Open INI editor", parent=self)
        self.star_btn = FavoriteActionButton(parent=self)
        self.edit_card_btn = CardActionButton("phosphor:regular:pencil-simple", "Customize", parent=self)
        self.folder_btn.clicked.connect(self.folder_clicked.emit)
        self.ini_btn.clicked.connect(self.ini_clicked.emit)
        self.star_btn.clicked.connect(self._on_pin_click)
        self.edit_card_btn.clicked.connect(lambda: self.customization_requested.emit(self.state_id))
        for button in (self.folder_btn, self.ini_btn, self.star_btn, self.edit_card_btn):
            actions.addWidget(button)
        header.addLayout(actions)

        self.avatar_circle = QFrame(self)
        self.avatar_circle.setFixedSize(48, 48)
        avatar_layout = QVBoxLayout(self.avatar_circle)
        avatar_layout.setContentsMargins(0, 0, 0, 0)
        self.avatar_lbl = QLabel(self._get_initials(self._display_name), self.avatar_circle)
        self.avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_layout.addWidget(self.avatar_lbl)
        self.avatar_icon = VectorIcon(
            custom_icon or "store", color="#F3F4F6", size=26, parent=self.avatar_circle
        )
        avatar_layout.addWidget(self.avatar_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        self.avatar_icon.setVisible(bool(custom_icon))
        self.avatar_lbl.setVisible(not custom_icon)
        self.avatar_status_dot = QFrame(self.avatar_circle)
        self.avatar_status_dot.setFixedSize(10, 10)
        self.avatar_status_dot.move(37, 37)
        self.avatar_status_dot.raise_()
        top_layout.addWidget(self.avatar_circle, alignment=Qt.AlignmentFlag.AlignHCenter)
        top_layout.addStretch()
        root.addWidget(self.top_content)

        # Theme-aware information panel. Its stepped silhouette is painted below.
        self.bottom_content = QWidget(self)
        self.bottom_content.setStyleSheet("background: transparent; border: none;")
        body = QVBoxLayout(self.bottom_content)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(3)

        self.kind_lbl = QLabel(self._display_name.upper(), self)
        self.kind_lbl.setFixedHeight(24)
        self.kind_lbl.setStyleSheet(
            "color: #F8FAFC; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 14px; font-weight: 800; letter-spacing: 0.5px; "
            "background: transparent; border: none;"
        )
        self.meta_lbl = QLabel("SHORTCUT  /  READY", self)
        self.meta_lbl.setStyleSheet(
            "color: #94A3B8; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 9px; font-weight: 700; background: transparent; border: none;"
        )

        identity_row = QHBoxLayout()
        identity_row.setContentsMargins(0, 0, 0, 0)
        identity_row.setSpacing(12)
        identity_copy = QVBoxLayout()
        identity_copy.setContentsMargins(0, 0, 0, 0)
        identity_copy.setSpacing(0)
        identity_copy.addWidget(self.kind_lbl)
        identity_copy.addWidget(self.meta_lbl)
        identity_row.addLayout(identity_copy)
        identity_row.addStretch()

        action_column = QVBoxLayout()
        action_column.setContentsMargins(0, 17, 0, 0)
        action_column.setSpacing(0)
        action_column.addLayout(header)
        action_column.addStretch()
        identity_row.addLayout(action_column)
        body.addLayout(identity_row)
        self.identity_rail = QFrame(self)
        self.identity_rail.hide()

        # Compatibility handles retained for existing tests and integrations.
        self.title_lbl = QLabel(self._display_name.upper(), self)
        self.title_lbl.hide()
        self.cursor_bar = QFrame(self)
        self.cursor_bar.setFixedSize(10, 3)
        self._update_cursor_style()
        self.cursor_bar.hide()
        self.path_lbl = QLabel(self)
        self.path_lbl.hide()

        body.addStretch(1)
        footer = QHBoxLayout()
        footer.setContentsMargins(0, 2, 0, 0)
        footer.setSpacing(8)
        self.code_lbl = QLabel(self._get_initials(self._display_name), self)
        self.code_lbl.setStyleSheet(
            "color: #142033; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 20px; font-weight: 800; background: transparent; border: none;"
        )
        footer.addWidget(self.code_lbl)
        footer.addStretch()
        self.status_badge = QLabel(self)
        self.pin_label = QLabel(self)
        self.mode_label = QLabel(self)
        for label in (self.status_badge, self.pin_label, self.mode_label):
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setFixedHeight(25)
            footer.addWidget(label)
        body.addLayout(footer)
        root.addWidget(self.bottom_content, 1)
        self._load_background()
        self._update_path_text()
        self._update_visuals()

    def get_card_hover_progress(self):
        return self._hover_progress

    def set_card_hover_progress(self, value):
        self._hover_progress = max(0.0, min(1.0, float(value)))
        self.update()

    cardHoverProgress = Property(float, get_card_hover_progress, set_card_hover_progress)

    def get_grid_offset(self):
        return self._grid_offset

    def set_grid_offset(self, value):
        self._grid_offset = float(value)
        self.update()

    gridOffset = Property(float, get_grid_offset, set_grid_offset)

    def _animate_card_to(self, target):
        self._hover_animation.stop()
        self._hover_animation.setStartValue(self._hover_progress)
        self._hover_animation.setEndValue(target)
        self._hover_animation.start()

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self._update_cursor_style()

    def _update_cursor_style(self):
        alpha = 255 if self._cursor_visible else 0
        self.cursor_bar.setStyleSheet(
            f"background: rgba(38, 132, 255, {alpha}); border: none; border-radius: 1px;"
        )

    def _load_background(self):
        self._background_pixmap = QPixmap()
        if self.custom_background and os.path.isfile(self.custom_background):
            loaded = QPixmap(self.custom_background)
            if not loaded.isNull():
                self._background_pixmap = loaded
        self._scaled_background = None
        self._scaled_background_size = None

    def _background_for_size(self, width, height):
        if self._background_pixmap.isNull():
            return None
        size_key = (max(1, int(width)), max(1, int(height)))
        if self._scaled_background is None or self._scaled_background_size != size_key:
            self._scaled_background = self._background_pixmap.scaled(
                size_key[0], size_key[1],
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._scaled_background_size = size_key
        return self._scaled_background
    def _update_path_text(self):
        path = self._full_subtitle or "Path unavailable"
        available = max(96, int((self.width() - 40) * 0.46))
        title = self._display_name.upper()
        display = self.kind_lbl.fontMetrics().elidedText(
            title, Qt.TextElideMode.ElideRight, available
        )
        self.kind_lbl.setText(display)
        self.kind_lbl.setToolTip(f"{self._display_name}\n{path}")
        self.path_lbl.clear()
        self.path_lbl.setToolTip("")
    def _get_initials(self, name):
        import re
        parts = [part for part in re.split(r"[\s_\-]+", name.strip()) if part]
        generic = {"RK7", "PRO", "APP", "SHORTCUT"}
        meaningful = [part for part in parts if part.upper() not in generic] or parts
        if len(meaningful) >= 2:
            return (meaningful[0][0] + meaningful[1][0]).upper()
        if meaningful:
            compact = re.sub(r"[^A-Za-z0-9]", "", meaningful[0])
            return compact[:2].upper()
        return "R7"

    def _tag_style(self, color, red, green, blue):
        return (
            f"color: {color}; background: rgba({red}, {green}, {blue}, 24); "
            f"border: 1px solid rgba({red}, {green}, {blue}, 58); border-radius: 6px; "
            "padding: 0 8px; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 9px; font-weight: 800;"
        )

    def _update_visuals(self):
        accent = self.custom_color or "#2684FF"
        self.avatar_circle.setStyleSheet(
            "background: rgba(255, 255, 255, 8); border: 1px solid rgba(255, 255, 255, 28); "
            "border-radius: 8px;"
        )
        self.avatar_lbl.setStyleSheet(
            "color: #F3F4F6; font-size: 12px; font-weight: 900; background: transparent; border: none;"
        )
        if self.custom_icon:
            self.avatar_icon.set_icon_name(self.custom_icon)
        self.avatar_icon.set_color("#F3F4F6")
        self.avatar_icon.setVisible(bool(self.custom_icon))
        self.avatar_lbl.setVisible(not self.custom_icon)
        self.avatar_circle.setVisible(self._background_pixmap.isNull())

        dot_color = SUCCESS if self.is_active else ("#FBBF24" if self.is_pinned else "transparent")
        self.avatar_status_dot.setStyleSheet(
            f"background: {dot_color}; border: 2px solid #0C111D; border-radius: 4px;"
        )
        self.avatar_status_dot.setVisible(self.is_active or self.is_pinned)
        self.avatar_status_dot.raise_()

        status = "RUNNING" if self.is_active else ("READY" if self.mode == "launch" else "FOLDER")
        self.meta_lbl.setText(f"SHORTCUT  /  {status}")
        self.code_lbl.setText(self._get_initials(self._display_name))
        
        # High contrast text for dark/light mode
        title_color = "#F8FAFC" if is_dark_mode() else "#142033"
        meta_color = "#94A3B8" if is_dark_mode() else "#475569"
        code_color = "#F8FAFC" if is_dark_mode() else "#142033"
        self.kind_lbl.setStyleSheet(
            f"color: {title_color}; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 14px; font-weight: 800; letter-spacing: 0.5px; background: transparent; border: none;"
        )
        self.meta_lbl.setStyleSheet(
            f"color: {meta_color}; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 9px; font-weight: 700; background: transparent; border: none;"
        )
        self.code_lbl.setStyleSheet(
            f"color: {code_color}; font-family: 'JetBrains Mono', Consolas, monospace; "
            "font-size: 20px; font-weight: 900; background: transparent; border: none;"
        )

        if self.is_active:
            self.status_badge.setStyleSheet(self._tag_style("#10B981", 16, 185, 129))
        else:
            self.status_badge.setStyleSheet(self._tag_style("#3B82F6", 59, 130, 246))
        self.status_badge.setText(status)

        self.pin_label.setText("PINNED" if self.is_pinned else "STANDARD")
        if self.is_pinned:
            self.pin_label.setStyleSheet(self._tag_style("#FBBF24", 251, 191, 36))
        else:
            self.pin_label.setStyleSheet(self._tag_style("#9CA3AF", 156, 163, 175))

        self.mode_label.setText("LAUNCH" if self.mode == "launch" else "DIRECTORY")
        self.mode_label.setStyleSheet(self._tag_style(accent, 38, 132, 255))
        self.star_btn.set_active(self.is_pinned)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        outer = QRectF(self.rect()).adjusted(6, 5, -6, -8)
        radius = 20.0
        shell = QPainterPath()
        shell.addRoundedRect(outer, radius, radius)

        # Lightweight painted shadow keeps scrolling fast.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 28))
        painter.drawRoundedRect(outer.translated(0, 2), radius, radius)

        painter.setPen(Qt.PenStyle.NoPen)
        panel_color = QColor("#13161C" if is_dark_mode() else "#FFFFFF")
        painter.setBrush(panel_color)
        painter.drawPath(shell)

        painter.save()
        painter.setClipPath(shell)
        inner = outer
        artwork = QRectF(
            inner.left(), inner.top(), inner.width(),
            min(132.0, inner.height() * 0.60)
        )

        if not self._background_pixmap.isNull():
            # Crop from the original source and scale only once. This avoids the
            # second low-resolution stretch that caused jagged edges on HiDPI.
            source_width = float(self._background_pixmap.width())
            source_height = float(self._background_pixmap.height())
            target_ratio = artwork.width() / max(1.0, artwork.height())
            source_ratio = source_width / max(1.0, source_height)
            if source_ratio > target_ratio:
                crop_width = source_height * target_ratio
                source_rect = QRectF(
                    (source_width - crop_width) / 2.0, 0.0,
                    crop_width, source_height,
                )
            else:
                crop_height = source_width / target_ratio
                source_rect = QRectF(
                    0.0, (source_height - crop_height) / 2.0,
                    source_width, crop_height,
                )
            painter.drawPixmap(artwork, self._background_pixmap, source_rect)
        else:
            palette = (
                "#FF7448", "#7257F5", "#2F80ED", "#14B8A6",
                "#EC4899", "#F59E0B", "#06B6D4", "#8B5CF6"
            )
            digest = hashlib.md5(self.name.encode("utf-8")).digest()[0]
            accent = QColor(self.custom_color or palette[digest % len(palette)])
            second = accent.lighter(145)
            gradient = QLinearGradient(artwork.topLeft(), artwork.bottomRight())
            gradient.setColorAt(0.0, second)
            gradient.setColorAt(0.55, accent)
            gradient.setColorAt(1.0, accent.darker(120))
            painter.setBrush(QBrush(gradient))
            painter.drawRect(artwork)

            glow = QRadialGradient(
                artwork.right() - artwork.width() * 0.18,
                artwork.top() + artwork.height() * 0.20,
                artwork.width() * 0.58,
            )
            glow.setColorAt(0.0, QColor(255, 255, 255, 92))
            glow.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(glow))
            painter.drawRect(artwork)


        # Folder-like lower panel: raised title tab on the left, themed body.
        left = inner.left()
        right = inner.right()
        bottom = inner.bottom()
        panel_top = outer.top() + 100.0
        panel_low = outer.top() + 130.0
        shoulder = left + inner.width() * 0.45
        curve_end = left + inner.width() * 0.59

        panel = QPainterPath()
        panel.moveTo(left, panel_top + 15)
        panel.quadTo(left, panel_top, left + 15, panel_top)
        panel.lineTo(shoulder, panel_top)
        panel.cubicTo(
            shoulder + 25, panel_top,
            curve_end - 28, panel_low,
            curve_end, panel_low,
        )
        panel.lineTo(right - 15, panel_low)
        panel.quadTo(right, panel_low, right, panel_low + 15)
        panel.lineTo(right, bottom - 15)
        panel.quadTo(right, bottom, right - 15, bottom)
        panel.lineTo(left + 15, bottom)
        panel.quadTo(left, bottom, left, bottom - 15)
        panel.closeSubpath()
        painter.setBrush(panel_color)
        painter.drawPath(panel)
        painter.restore()

        if self.is_selected:
            border_color, width = QColor("#3B82F6"), 2.0
        elif self.is_active:
            border_color, width = QColor("#10B981"), 1.8
        else:
            base = QColor("#1E232D" if is_dark_mode() else "#E2E8F0")
            hover = QColor("#3B82F6")
            p = self._hover_progress
            border_color = QColor(
                round(base.red() + (hover.red() - base.red()) * p),
                round(base.green() + (hover.green() - base.green()) * p),
                round(base.blue() + (hover.blue() - base.blue()) * p),
            )
            width = 1.0
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(border_color, width))
        painter.drawRoundedRect(outer, radius, radius)
    def set_selected(self, selected):
        self.is_selected = selected
        self.update()

    def trigger_launch_feedback(self):
        self.is_active = True
        self._update_visuals()
        self.status_badge.setText("LAUNCHING")

    def update_info(self, subtitle, is_pinned, is_active, custom_name=None, custom_color=None,
                    custom_icon=None, custom_background=None):
        self._full_subtitle = subtitle
        self.is_pinned = is_pinned
        self.is_active = is_active
        self.custom_name = custom_name
        self.custom_color = custom_color
        self.custom_icon = custom_icon
        self.custom_background = custom_background
        self._load_background()
        self._display_name = custom_name or self.name
        self.title_lbl.setText(self._display_name.upper())
        self.avatar_lbl.setText(self._get_initials(self._display_name))
        self._update_path_text()
        self._update_visuals()

    def _on_pin_click(self):
        self.is_pinned = not self.is_pinned
        self._update_visuals()
        self.pin_toggled.emit(self.is_pinned)

    def enterEvent(self, event):
        self._animate_card_to(1.0)
        self._cursor_visible = True
        self._update_cursor_style()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_card_to(0.0)
        self.set_grid_offset(0.0)
        self._cursor_visible = True
        self._update_cursor_style()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_path_text()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.mode == "launch":
                self.trigger_launch_feedback()
            self.clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        customize_action = menu.addAction("Customize shortcut")
        action = menu.exec(event.globalPos())
        if action == customize_action:
            self.customization_requested.emit(self.state_id)