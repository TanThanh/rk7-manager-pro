from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout
from PySide6.QtCore import Qt, Signal as pyqtSignal, Property, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QBrush
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import (
    BRAND_RED, TEXT_MAIN, TEXT_SEC, TEXT_MUTED, BORDER_COLOR, CARD_HOVER, SUCCESS, WARNING
)
from rk7_pro.components.icons import VectorIcon


class MetricTile(QFrame):
    def __init__(self, label, color, parent=None):
        super().__init__(parent)
        self.setFixedSize(110, 52)
        self.setStyleSheet(
            f"background: #13161C; border: 1px solid #1E232D; border-radius: 12px;"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 7, 12, 7)
        row.setSpacing(10)
        accent = QFrame(self)
        accent.setFixedSize(3, 28)
        accent.setStyleSheet(f"background: {color}; border-radius: 2px; border: none;")
        row.addWidget(accent)
        copy = QVBoxLayout()
        copy.setSpacing(1)
        self.value_lbl = QLabel("0", self)
        self.value_lbl.setStyleSheet(
            f"color: #F8FAFC; font-size: 16px; font-weight: 800; border: none; background: transparent;"
        )
        label_lbl = QLabel(label, self)
        label_lbl.setStyleSheet(
            f"color: #64748B; font-size: 8px; font-weight: 800; letter-spacing: 0.8px; "
            "border: none; background: transparent;"
        )
        copy.addWidget(self.value_lbl)
        copy.addWidget(label_lbl)
        row.addLayout(copy)

    def set_value(self, value):
        self.value_lbl.setText(str(value))


class HeaderIconBtn(QPushButton):
    def __init__(self, icon_name, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"""
            QPushButton {{
                background: #13161C;
                border: 1px solid #1E232D;
                border-radius: 10px;
            }}
            QPushButton:hover {{ background: #181C24; border-color: #2D3748; }}
            QPushButton:focus {{ border-color: {BRAND_RED}; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(VectorIcon(icon_name, color="#94A3B8", size=16, parent=self),
                      alignment=Qt.AlignmentFlag.AlignCenter)


class ThemeToggle(QPushButton):
    """Animated day/night switch inspired by the supplied Uiverse control."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self.setFixedSize(74, 36)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip("Switch to dark mode")
        self.setAccessibleName("Toggle dark mode")
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

        self._animation = QPropertyAnimation(self, b"themeProgress", self)
        self._animation.setDuration(380)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_state)

    @staticmethod
    def _mix(start_hex, end_hex, amount):
        start = QColor(start_hex)
        end = QColor(end_hex)
        amount = max(0.0, min(1.0, amount))
        return QColor(
            round(start.red() + (end.red() - start.red()) * amount),
            round(start.green() + (end.green() - start.green()) * amount),
            round(start.blue() + (end.blue() - start.blue()) * amount),
        )

    def get_theme_progress(self):
        return self._progress

    def set_theme_progress(self, value):
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    themeProgress = Property(float, get_theme_progress, set_theme_progress)

    def _animate_state(self, dark):
        self.setToolTip("Switch to light mode" if dark else "Switch to dark mode")
        self._animation_target = 1.0 if dark else 0.0
        # Let the palette swap finish first, then animate on a free event loop.
        QTimer.singleShot(0, self._start_animation)

    def _start_animation(self):
        self._animation.stop()
        self._animation.setStartValue(self._progress)
        self._animation.setEndValue(self._animation_target)
        self._animation.start()

    def set_dark(self, dark, animate=True):
        dark = bool(dark)
        self.blockSignals(True)
        self.setChecked(dark)
        self.blockSignals(False)
        self.setToolTip("Switch to light mode" if dark else "Switch to dark mode")
        if animate:
            self._animate_state(dark)
        else:
            self._animation.stop()
            self.set_theme_progress(1.0 if dark else 0.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        track = self.rect().adjusted(1, 2, -1, -2)
        background = self._mix("#3D7EAE", "#1D1F2C", self._progress)
        painter.setPen(QPen(QColor("#263449"), 1.0))
        painter.setBrush(QBrush(background))
        painter.drawRoundedRect(track, 17, 17)

        # Day clouds drift down and fade as night arrives.
        painter.save()
        painter.setOpacity(1.0 - self._progress)
        cloud_y = 25 + 10 * self._progress
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#F3FDFF")))
        for x, radius in ((30, 7), (39, 9), (50, 6), (59, 8)):
            painter.drawEllipse(int(x - radius), int(cloud_y - radius / 2), radius * 2, radius)
        painter.restore()

        # Stars descend into view in dark mode.
        painter.save()
        painter.setOpacity(self._progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#FFFFFF")))
        for x, y, size in ((10, 10, 2), (18, 23, 2), (28, 8, 3), (36, 18, 2)):
            painter.drawEllipse(x, int(y - 6 * (1.0 - self._progress)), size, size)
        painter.restore()

        center_x = 18 + 38 * self._progress
        center_y = self.height() / 2.0
        halo = QColor(255, 255, 255, 28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(int(center_x - 17), int(center_y - 17), 34, 34)
        painter.setBrush(QBrush(QColor(255, 255, 255, 24)))
        painter.drawEllipse(int(center_x - 14), int(center_y - 14), 28, 28)

        orb = self._mix("#ECCA2F", "#C4C9D1", self._progress)
        painter.setBrush(QBrush(orb))
        painter.setPen(QPen(QColor(0, 0, 0, 45), 1.0))
        painter.drawEllipse(int(center_x - 11), int(center_y - 11), 22, 22)

        painter.save()
        painter.setOpacity(self._progress)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor("#959DB1")))
        painter.drawEllipse(int(center_x - 6), int(center_y - 4), 6, 6)
        painter.drawEllipse(int(center_x + 3), int(center_y + 2), 3, 3)
        painter.drawEllipse(int(center_x - 1), int(center_y - 8), 3, 3)
        painter.restore()

        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(BRAND_RED), 2.0))
            painter.drawRoundedRect(track.adjusted(1, 1, -1, -1), 16, 16)

class TopHeader(QFrame):
    settings_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(76)
        self.setStyleSheet("background: transparent; border: none;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(28, 12, 28, 8)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        copy.setSpacing(1)
        eyebrow = QLabel("FILE & SHORTCUT MANAGER", self)
        eyebrow.setStyleSheet(
            f"color: #3B82F6; font-size: 9px; font-weight: 800; letter-spacing: 1.2px; border: none;"
        )
        self.title_lbl = QLabel("Shortcut Library", self)
        self.title_lbl.setStyleSheet(
            f"color: #F8FAFC; font-size: 22px; font-weight: 800; border: none;"
        )
        self.subtitle_lbl = QLabel("Launch and monitor environments from one place", self)
        self.subtitle_lbl.setStyleSheet(
            f"color: #64748B; font-size: 11px; font-weight: 500; border: none;"
        )
        copy.addWidget(eyebrow)
        copy.addWidget(self.title_lbl)
        copy.addWidget(self.subtitle_lbl)
        layout.addLayout(copy)
        layout.addStretch()

        self.total_metric = MetricTile("ALL", "#94A3B8", self)
        self.running_metric = MetricTile("RUNNING", "#10B981", self)
        self.pinned_metric = MetricTile("PINNED", "#F59E0B", self)
        layout.addWidget(self.total_metric)
        layout.addWidget(self.running_metric)
        layout.addWidget(self.pinned_metric)

        self.theme_toggle = ThemeToggle(self)
        layout.addWidget(self.theme_toggle, alignment=Qt.AlignmentFlag.AlignVCenter)

        self.avatar_btn = HeaderIconBtn("settings", self)
        self.avatar_btn.setToolTip("Open settings")
        self.avatar_btn.clicked.connect(self.settings_requested.emit)
        self.theme_btn = self.avatar_btn
        # Settings already has a dedicated sidebar destination.
        self.avatar_btn.hide()

        # Compatibility alias used by refresh feedback.
        self.count_lbl = QLabel(self)
        self.count_lbl.hide()

    def set_context(self, title, subtitle):
        self.title_lbl.setText(title)
        self.subtitle_lbl.setText(subtitle)

    def set_count(self, count):
        self.total_metric.set_value(count)

    def set_metrics(self, total, running, pinned):
        self.total_metric.set_value(total)
        self.running_metric.set_value(running)
        self.pinned_metric.set_value(pinned)