# rk7_pro/components/icons.py
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QPen, QColor, QBrush, QPainterPath
from PySide6.QtCore import Qt, QSize, QRectF
import math
from rk7_pro.theme_manager import theme_color
from rk7_pro.components.phosphor_icons import paint_phosphor_icon

class VectorIcon(QWidget):
    def __init__(self, icon_name, color="#475569", size=20, parent=None):
        super().__init__(parent)
        self.icon_name = icon_name.lower()
        self.color = color
        self.icon_size = size
        self.setFixedSize(size, size)
        
    def set_color(self, color):
        if self.color != color:
            self.color = color
            self.update()

    def set_icon_name(self, icon_name):
        icon_name = icon_name.lower()
        if self.icon_name != icon_name:
            self.icon_name = icon_name
            self.update()
            
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        pen = QPen(QColor(theme_color(self.color)))
        pen.setWidthF(1.9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        
        w = float(self.width())
        h = float(self.height())

        if paint_phosphor_icon(
            painter, QRectF(0, 0, w, h), self.icon_name, theme_color(self.color)
        ):
            return
        
        if self.icon_name in ("launch", "rocket"):
            # Rocket
            path = QPainterPath()
            # Left wing
            path.moveTo(w * 0.35, h * 0.55)
            path.lineTo(w * 0.22, h * 0.72)
            path.lineTo(w * 0.35, h * 0.72)
            # Body outline
            path.moveTo(w * 0.35, h * 0.72)
            path.cubicTo(w * 0.35, h * 0.40, w * 0.40, h * 0.18, w * 0.50, h * 0.12)
            path.cubicTo(w * 0.60, h * 0.18, w * 0.65, h * 0.40, w * 0.65, h * 0.72)
            # Right wing
            path.moveTo(w * 0.65, h * 0.55)
            path.lineTo(w * 0.78, h * 0.72)
            path.lineTo(w * 0.65, h * 0.72)
            # Base and nozzle
            path.moveTo(w * 0.38, h * 0.72)
            path.lineTo(w * 0.62, h * 0.72)
            path.moveTo(w * 0.45, h * 0.72)
            path.lineTo(w * 0.42, h * 0.82)
            path.lineTo(w * 0.58, h * 0.82)
            path.lineTo(w * 0.55, h * 0.72)
            # Center window/dot
            painter.drawPath(path)
            painter.drawEllipse(int(w * 0.45), int(h * 0.38), int(w * 0.1), int(h * 0.1))
            
        elif self.icon_name in ("folders", "folder"):
            # Rounded, open folder silhouette.
            path = QPainterPath()
            path.moveTo(w * 0.14, h * 0.72)
            path.lineTo(w * 0.14, h * 0.30)
            path.quadTo(w * 0.14, h * 0.22, w * 0.23, h * 0.22)
            path.lineTo(w * 0.42, h * 0.22)
            path.lineTo(w * 0.51, h * 0.34)
            path.lineTo(w * 0.78, h * 0.34)
            path.quadTo(w * 0.86, h * 0.34, w * 0.84, h * 0.43)
            path.lineTo(w * 0.77, h * 0.74)
            path.quadTo(w * 0.75, h * 0.80, w * 0.67, h * 0.80)
            path.lineTo(w * 0.22, h * 0.80)
            path.quadTo(w * 0.14, h * 0.80, w * 0.14, h * 0.72)
            path.closeSubpath()
            painter.drawPath(path)
            
        elif self.icon_name in ("settings", "gear"):
            # Gear
            cx, cy = w / 2.0, h / 2.0
            r_out = w * 0.35
            r_in = w * 0.18
            
            # Draw center circle
            painter.drawEllipse(int(cx - r_in), int(cy - r_in), int(r_in * 2), int(r_in * 2))
            
            # Teeth paths
            path = QPainterPath()
            teeth = 8
            for i in range(teeth):
                angle = i * (2 * math.pi / teeth)
                a1 = angle - 0.18
                a2 = angle + 0.18
                
                x1 = cx + r_out * math.cos(a1)
                y1 = cy + r_out * math.sin(a1)
                x2 = cx + r_out * math.cos(a2)
                y2 = cy + r_out * math.sin(a2)
                
                x0 = cx + (r_in + 2) * math.cos(a1 - 0.1)
                y0 = cy + (r_in + 2) * math.sin(a1 - 0.1)
                x3 = cx + (r_in + 2) * math.cos(a2 + 0.1)
                y3 = cy + (r_in + 2) * math.sin(a2 + 0.1)
                
                if i == 0:
                    path.moveTo(x0, y0)
                else:
                    path.lineTo(x0, y0)
                path.lineTo(x1, y1)
                path.lineTo(x2, y2)
                path.lineTo(x3, y3)
            path.closeSubpath()
            painter.drawPath(path)
            
        elif self.icon_name in ("bell", "notification"):
            # Bell
            path = QPainterPath()
            path.moveTo(w * 0.25, h * 0.70)
            path.cubicTo(w * 0.25, h * 0.32, w * 0.75, h * 0.32, w * 0.75, h * 0.70)
            path.lineTo(w * 0.82, h * 0.75)
            path.lineTo(w * 0.18, h * 0.75)
            path.closeSubpath()
            painter.drawPath(path)
            # Clapper
            clapper = QPainterPath()
            clapper.moveTo(w * 0.42, h * 0.78)
            clapper.arcTo(w * 0.42, h * 0.72, w * 0.16, h * 0.16, 180, 180)
            painter.drawPath(clapper)
            # Small ring loop at top
            painter.drawEllipse(int(w * 0.46), int(h * 0.16), int(w * 0.08), int(h * 0.08))
            
        elif self.icon_name in ("user", "profile"):
            # User profile silhouette
            painter.drawEllipse(int(w * 0.36), int(h * 0.22), int(w * 0.28), int(h * 0.28))
            path = QPainterPath()
            path.moveTo(w * 0.20, h * 0.76)
            path.cubicTo(w * 0.25, h * 0.55, w * 0.75, h * 0.55, w * 0.80, h * 0.76)
            painter.drawPath(path)
            
        elif self.icon_name in ("chevron_right", "chevron"):
            # Chevron angle
            path = QPainterPath()
            path.moveTo(w * 0.38, h * 0.28)
            path.lineTo(w * 0.62, h * 0.50)
            path.lineTo(w * 0.38, h * 0.72)
            painter.drawPath(path)
            
        elif self.icon_name == "plus":
            # Plus icon
            painter.drawLine(int(w * 0.25), int(h * 0.50), int(w * 0.75), int(h * 0.50))
            painter.drawLine(int(w * 0.50), int(h * 0.25), int(w * 0.50), int(h * 0.75))
            
        elif self.icon_name in ("edit", "pencil"):
            # Edit pencil
            path = QPainterPath()
            path.moveTo(w * 0.25, h * 0.65)
            path.lineTo(w * 0.60, h * 0.30)
            path.lineTo(w * 0.70, h * 0.40)
            path.lineTo(w * 0.35, h * 0.75)
            path.lineTo(w * 0.22, h * 0.78)
            path.closeSubpath()
            painter.drawPath(path)
            # Detail lines
            painter.drawLine(int(w * 0.55), int(h * 0.35), int(w * 0.65), int(h * 0.45))
            
        elif self.icon_name == "save":
            # Floppy diskette save icon
            path = QPainterPath()
            path.moveTo(w * 0.22, h * 0.78)
            path.lineTo(w * 0.22, h * 0.25)
            path.lineTo(w * 0.68, h * 0.25)
            path.lineTo(w * 0.78, h * 0.35)
            path.lineTo(w * 0.78, h * 0.78)
            path.closeSubpath()
            painter.drawPath(path)
            # Center label square
            painter.drawRect(int(w * 0.35), int(h * 0.50), int(w * 0.30), int(h * 0.28))
            # Top slider
            painter.drawRect(int(w * 0.38), int(h * 0.25), int(w * 0.20), int(h * 0.15))
            
        elif self.icon_name in ("search", "find"):
            # Search magnifying glass
            painter.drawEllipse(int(w * 0.28), int(h * 0.28), int(w * 0.35), int(h * 0.35))
            painter.drawLine(int(w * 0.58), int(h * 0.58), int(w * 0.76), int(h * 0.76))

        elif self.icon_name in ("star", "bookmark", "bookmark_filled"):
            # Bookmark communicates a persistent favorite more clearly than a tiny star.
            path = QPainterPath()
            path.moveTo(w * 0.28, h * 0.18)
            path.quadTo(w * 0.28, h * 0.12, w * 0.36, h * 0.12)
            path.lineTo(w * 0.64, h * 0.12)
            path.quadTo(w * 0.72, h * 0.12, w * 0.72, h * 0.20)
            path.lineTo(w * 0.72, h * 0.84)
            path.lineTo(w * 0.50, h * 0.69)
            path.lineTo(w * 0.28, h * 0.84)
            path.closeSubpath()
            if self.icon_name in ("star", "bookmark_filled"):
                painter.setBrush(QBrush(QColor(theme_color(self.color))))
            painter.drawPath(path)

        elif self.icon_name in ("file", "document"):
            # File / Document outline with corner fold
            path = QPainterPath()
            path.moveTo(w * 0.25, h * 0.15)
            path.lineTo(w * 0.60, h * 0.15)
            path.lineTo(w * 0.75, h * 0.30)
            path.lineTo(w * 0.75, h * 0.85)
            path.lineTo(w * 0.25, h * 0.85)
            path.closeSubpath()
            painter.drawPath(path)
            # Corner fold lines
            painter.drawLine(int(w * 0.60), int(h * 0.15), int(w * 0.60), int(h * 0.30))
            painter.drawLine(int(w * 0.60), int(h * 0.30), int(w * 0.75), int(h * 0.30))
            painter.drawLine(int(w * 0.36), int(h * 0.49), int(w * 0.64), int(h * 0.49))
            painter.drawLine(int(w * 0.36), int(h * 0.62), int(w * 0.61), int(h * 0.62))

        elif self.icon_name in ("close", "x", "cross"):
            # Draw X
            painter.drawLine(int(w * 0.30), int(h * 0.30), int(w * 0.70), int(h * 0.70))
            painter.drawLine(int(w * 0.70), int(h * 0.30), int(w * 0.30), int(h * 0.70))

        elif self.icon_name == "filter":
            path = QPainterPath()
            path.moveTo(w * 0.22, h * 0.25)
            path.lineTo(w * 0.78, h * 0.25)
            path.lineTo(w * 0.55, h * 0.50)
            path.lineTo(w * 0.55, h * 0.75)
            path.lineTo(w * 0.45, h * 0.75)
            path.lineTo(w * 0.45, h * 0.50)
            path.closeSubpath()
            painter.drawPath(path)

        elif self.icon_name == "grid":
            painter.drawRect(int(w * 0.22), int(h * 0.22), int(w * 0.22), int(h * 0.22))
            painter.drawRect(int(w * 0.56), int(h * 0.22), int(w * 0.22), int(h * 0.22))
            painter.drawRect(int(w * 0.22), int(h * 0.56), int(w * 0.22), int(h * 0.22))
            painter.drawRect(int(w * 0.56), int(h * 0.56), int(w * 0.22), int(h * 0.22))

        elif self.icon_name == "list":
            painter.drawLine(int(w * 0.22), int(h * 0.32), int(w * 0.30), int(h * 0.32))
            painter.drawLine(int(w * 0.42), int(h * 0.32), int(w * 0.78), int(h * 0.32))
            painter.drawLine(int(w * 0.22), int(h * 0.50), int(w * 0.30), int(h * 0.50))
            painter.drawLine(int(w * 0.42), int(h * 0.50), int(w * 0.78), int(h * 0.50))
            painter.drawLine(int(w * 0.22), int(h * 0.68), int(w * 0.30), int(h * 0.68))
            painter.drawLine(int(w * 0.42), int(h * 0.68), int(w * 0.78), int(h * 0.68))

        elif self.icon_name in ("arrow_left", "back"):
            painter.drawLine(int(w * 0.75), int(h * 0.5), int(w * 0.25), int(h * 0.5))
            painter.drawLine(int(w * 0.25), int(h * 0.5), int(w * 0.45), int(h * 0.3))
            painter.drawLine(int(w * 0.25), int(h * 0.5), int(w * 0.45), int(h * 0.7))

        elif self.icon_name in ("arrow_right", "forward"):
            painter.drawLine(int(w * 0.25), int(h * 0.5), int(w * 0.75), int(h * 0.5))
            painter.drawLine(int(w * 0.75), int(h * 0.5), int(w * 0.55), int(h * 0.3))
            painter.drawLine(int(w * 0.75), int(h * 0.5), int(w * 0.55), int(h * 0.7))

        elif self.icon_name in ("refresh", "reload", "rotate_cw"):
            path = QPainterPath()
            path.arcTo(int(w * 0.22), int(h * 0.22), int(w * 0.56), int(h * 0.56), 45, 270)
            painter.drawPath(path)
            # Arrow head
            arrow = QPainterPath()
            arrow.moveTo(w * 0.65, h * 0.30)
            arrow.lineTo(w * 0.78, h * 0.18)
            arrow.lineTo(w * 0.78, h * 0.38)
            arrow.closeSubpath()
            painter.save()
            painter.setBrush(QBrush(QColor(theme_color(self.color))))
            painter.drawPath(arrow)
            painter.restore()

        elif self.icon_name == "storefront":
            painter.drawLine(int(w * 0.18), int(h * 0.36), int(w * 0.82), int(h * 0.36))
            painter.drawLine(int(w * 0.25), int(h * 0.36), int(w * 0.25), int(h * 0.82))
            painter.drawLine(int(w * 0.75), int(h * 0.36), int(w * 0.75), int(h * 0.82))
            painter.drawLine(int(w * 0.25), int(h * 0.82), int(w * 0.75), int(h * 0.82))
            painter.drawRect(int(w * 0.43), int(h * 0.57), int(w * 0.18), int(h * 0.25))
            awning = QPainterPath()
            awning.moveTo(w * 0.18, h * 0.36)
            awning.lineTo(w * 0.26, h * 0.18)
            awning.lineTo(w * 0.74, h * 0.18)
            awning.lineTo(w * 0.82, h * 0.36)
            painter.drawPath(awning)

        elif self.icon_name == "coffee":
            painter.drawRoundedRect(int(w * 0.20), int(h * 0.38), int(w * 0.48), int(h * 0.36), 3, 3)
            painter.drawArc(int(w * 0.58), int(h * 0.43), int(w * 0.24), int(h * 0.22), -90 * 16, 180 * 16)
            painter.drawLine(int(w * 0.17), int(h * 0.80), int(w * 0.76), int(h * 0.80))
            painter.drawArc(int(w * 0.28), int(h * 0.14), int(w * 0.12), int(h * 0.30), 20 * 16, 115 * 16)
            painter.drawArc(int(w * 0.45), int(h * 0.12), int(w * 0.12), int(h * 0.30), 20 * 16, 115 * 16)

        elif self.icon_name == "restaurant":
            painter.drawLine(int(w * 0.30), int(h * 0.16), int(w * 0.30), int(h * 0.84))
            painter.drawLine(int(w * 0.20), int(h * 0.16), int(w * 0.20), int(h * 0.38))
            painter.drawLine(int(w * 0.40), int(h * 0.16), int(w * 0.40), int(h * 0.38))
            painter.drawArc(int(w * 0.20), int(h * 0.25), int(w * 0.20), int(h * 0.22), 180 * 16, 180 * 16)
            painter.drawLine(int(w * 0.67), int(h * 0.16), int(w * 0.67), int(h * 0.84))
            painter.drawArc(int(w * 0.50), int(h * 0.16), int(w * 0.34), int(h * 0.40), 90 * 16, 180 * 16)

        elif self.icon_name == "bridge":
            painter.drawLine(int(w * 0.14), int(h * 0.76), int(w * 0.86), int(h * 0.76))
            painter.drawLine(int(w * 0.22), int(h * 0.76), int(w * 0.22), int(h * 0.28))
            painter.drawLine(int(w * 0.78), int(h * 0.76), int(w * 0.78), int(h * 0.28))
            painter.drawLine(int(w * 0.14), int(h * 0.53), int(w * 0.86), int(h * 0.53))
            painter.drawArc(int(w * 0.22), int(h * 0.30), int(w * 0.56), int(h * 0.46), 0, 180 * 16)

        elif self.icon_name == "building":
            painter.drawRect(int(w * 0.24), int(h * 0.16), int(w * 0.52), int(h * 0.68))
            for x in (0.36, 0.58):
                for y in (0.30, 0.48):
                    painter.drawRect(int(w * x), int(h * y), int(w * 0.08), int(h * 0.08))
            painter.drawRect(int(w * 0.44), int(h * 0.66), int(w * 0.12), int(h * 0.18))

        elif self.icon_name == "monitor":
            painter.drawRoundedRect(int(w * 0.14), int(h * 0.18), int(w * 0.72), int(h * 0.52), 3, 3)
            painter.drawLine(int(w * 0.50), int(h * 0.70), int(w * 0.50), int(h * 0.82))
            painter.drawLine(int(w * 0.34), int(h * 0.82), int(w * 0.66), int(h * 0.82))

        elif self.icon_name == "server":
            painter.drawRoundedRect(int(w * 0.18), int(h * 0.16), int(w * 0.64), int(h * 0.28), 3, 3)
            painter.drawRoundedRect(int(w * 0.18), int(h * 0.56), int(w * 0.64), int(h * 0.28), 3, 3)
            painter.drawEllipse(int(w * 0.27), int(h * 0.25), int(w * 0.07), int(h * 0.07))
            painter.drawEllipse(int(w * 0.27), int(h * 0.65), int(w * 0.07), int(h * 0.07))
            painter.drawLine(int(w * 0.43), int(h * 0.30), int(w * 0.70), int(h * 0.30))
            painter.drawLine(int(w * 0.43), int(h * 0.70), int(w * 0.70), int(h * 0.70))

        elif self.icon_name == "globe":
            painter.drawEllipse(int(w * 0.14), int(h * 0.14), int(w * 0.72), int(h * 0.72))
            painter.drawEllipse(int(w * 0.34), int(h * 0.14), int(w * 0.32), int(h * 0.72))
            painter.drawLine(int(w * 0.16), int(h * 0.50), int(w * 0.84), int(h * 0.50))
            painter.drawArc(int(w * 0.18), int(h * 0.25), int(w * 0.64), int(h * 0.50), 0, 180 * 16)

        elif self.icon_name in ("trash", "clear"):
            # Draw lid
            painter.drawLine(int(w * 0.25), int(h * 0.28), int(w * 0.75), int(h * 0.28))
            painter.drawRect(int(w * 0.40), int(h * 0.18), int(w * 0.20), int(h * 0.10))
            # Draw body
            painter.drawRect(int(w * 0.30), int(h * 0.28), int(w * 0.40), int(h * 0.52))
            # Draw lines inside
            painter.drawLine(int(w * 0.42), int(h * 0.38), int(w * 0.42), int(h * 0.70))
            painter.drawLine(int(w * 0.50), int(h * 0.38), int(w * 0.50), int(h * 0.70))
            painter.drawLine(int(w * 0.58), int(h * 0.38), int(w * 0.58), int(h * 0.70))


