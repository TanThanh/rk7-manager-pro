# rk7_pro/components/editor.py
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QFrame, QTextEdit,
    QGraphicsDropShadowEffect
)
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QPainter, QTextFormat
from PySide6.QtCore import Qt, QRect, QSize, Signal as pyqtSignal
from datetime import datetime
import os, sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from rk7_pro.theme import EDITOR_BG, PANEL_BG, NEON_GREEN, TEXT_MAIN, TEXT_SEC, TEXT_MUTED, BORDER_COLOR, CARD_HOVER, FONT_MONO
from rk7_pro.components.icons import VectorIcon
from rk7_pro.theme_manager import theme_color

class IniHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rules = []

        # Sections [SECTION]
        section_fmt = QTextCharFormat()
        section_fmt.setForeground(QColor("#F9E2AF")) # Soft yellow
        section_fmt.setFontWeight(QFont.Weight.Bold)
        self.rules.append((r"\[[^\]]+\]", section_fmt))

        # Keys
        key_fmt = QTextCharFormat()
        key_fmt.setForeground(QColor("#89B4FA")) # Soft blue
        self.rules.append((r"^[a-zA-Z0-9_.-]+\s*=", key_fmt))

        # Values
        val_fmt = QTextCharFormat()
        val_fmt.setForeground(QColor("#A6E3A1")) # Soft green
        self.rules.append((r"=\s*.*$", val_fmt))

        # Comments
        comment_fmt = QTextCharFormat()
        comment_fmt.setForeground(QColor("#6C7086")) # Muted gray
        comment_fmt.setFontItalic(True)
        self.rules.append((r"//.*", comment_fmt))
        self.rules.append((r"#.*", comment_fmt))
        self.rules.append((r";.*", comment_fmt))

    def highlightBlock(self, text):
        import re
        for pattern, format in self.rules:
            for match in re.finditer(pattern, text):
                start = match.start()
                length = match.end() - start
                
                # If rule is "key=", we only want to highlight the key part, not the '='
                if pattern == r"^[a-zA-Z0-9_.-]+\s*=":
                    length -= 1
                elif pattern == r"=\s*.*$":
                    # For value, exclude the '='
                    start += 1
                    length -= 1
                    
                self.setFormat(start, length, format)


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)
        
        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)
        
        # Styling
        self.setStyleSheet(f"""
            QPlainTextEdit {{
                background-color: {EDITOR_BG};
                color: #E5E7EB;
                font-family: {FONT_MONO};
                font-size: 13px;
                border: none;
                selection-background-color: #26446F;
            }}
        """)
        
        self.document().setDocumentMargin(12)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)

        self.highlighter = IniHighlighter(self.document())
        self.highlight_current_line()


    def line_number_area_width(self):
        digits = 1
        m = max(1, self.blockCount())
        while m >= 10:
            m /= 10
            digits += 1
        space = 25 + self.fontMetrics().horizontalAdvance('9') * digits
        return space

    def update_line_number_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def update_line_number_area(self, rect, dy):
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_line_number_area_width(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        cr = self.contentsRect()
        self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))

    def highlight_current_line(self):
        extra_selections = []
        if not self.isReadOnly():
            selection = QTextEdit.ExtraSelection()
            line_color = QColor("#172033")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#0B1220"))

        
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor(TEXT_MUTED))
                painter.setFont(self.font())
                painter.drawText(0, top, self.line_number_area.width() - 12, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number)
            
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class EditorFooter(QFrame):
    """Compact metadata and save-state footer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: #F8FAFC;
                border-top: 1px solid {BORDER_COLOR};
            }}
            QLabel {{
                color: {TEXT_MUTED};
                font-size: 10px;
                font-weight: 700;
                border: none;
                background: transparent;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(10)

        self.type_lbl = QLabel("INI", self)
        self.type_lbl.setStyleSheet(
            "color: #2563EB; background: rgba(37, 99, 235, 20); border: 1px solid rgba(37, 99, 235, 54); "
            "border-radius: 6px; padding: 3px 7px; font-size: 9px; font-weight: 800;"
        )
        self.lines_lbl = QLabel("0 LINES", self)
        self.encoding_lbl = QLabel("ANSI", self)
        layout.addWidget(self.type_lbl)
        layout.addWidget(self.lines_lbl)
        layout.addWidget(self.encoding_lbl)
        layout.addStretch()

        self.time_lbl = QLabel("NOT SAVED YET", self)
        layout.addWidget(self.time_lbl)

        status_wrap = QWidget(self)
        status_wrap.setStyleSheet("border: none; background: transparent;")
        sw_layout = QHBoxLayout(status_wrap)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        sw_layout.setSpacing(6)
        self.dot = QFrame(status_wrap)
        self.dot.setFixedSize(7, 7)
        sw_layout.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.status_lbl = QLabel("SAVED", status_wrap)
        sw_layout.addWidget(self.status_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(status_wrap)
        self.mark_saved(True)

    def update_lines(self, count):
        self.lines_lbl.setText(f"{count} LINES")

    def mark_saved(self, is_saved=True):
        if is_saved:
            color = "#059669"
            self.status_lbl.setText("SAVED")
            self.dot.setStyleSheet(f"background: {color}; border-radius: 3px; border: none;")
            self.status_lbl.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: 800; border: none;"
            )
            self.time_lbl.setText(datetime.now().strftime("SAVED %I:%M %p"))
        else:
            color = "#D97706"
            self.status_lbl.setText("UNSAVED")
            self.dot.setStyleSheet(f"background: {color}; border-radius: 3px; border: none;")
            self.status_lbl.setStyleSheet(
                f"color: {color}; font-size: 10px; font-weight: 800; border: none;"
            )
            self.time_lbl.setText("CHANGES NOT SAVED")

    def mark_error(self, message=""):
        color = "#DC2626"
        self.status_lbl.setText("SAVE FAILED")
        self.dot.setStyleSheet(f"background: {color}; border-radius: 3px; border: none;")
        self.status_lbl.setStyleSheet(
            f"color: {color}; font-size: 10px; font-weight: 800; border: none;"
        )
        self.time_lbl.setText("COULD NOT SAVE")
        self.time_lbl.setToolTip(message)

class MainWorkspace(QFrame):
    save_requested = pyqtSignal(str) # content
    close_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("iniWorkspace")
        self.setStyleSheet(f"""
            QFrame#iniWorkspace {{
                background: #FFFFFF;
                border-left: 1px solid {BORDER_COLOR};
                border-top: none;
                border-bottom: none;
                border-right: none;
            }}
        """)

        # Compatibility handle only; do not attach a blur effect to the sliding drawer.
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(12)
        self.shadow.setColor(QColor(15, 23, 42, 35))
        self.shadow.setOffset(-2, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QFrame(self)
        toolbar.setObjectName("iniToolbar")
        toolbar.setFixedHeight(72)
        toolbar.setStyleSheet(f"""
            QFrame#iniToolbar {{
                background: #FFFFFF;
                border-bottom: 1px solid {BORDER_COLOR};
            }}
        """)
        t_layout = QHBoxLayout(toolbar)
        t_layout.setContentsMargins(16, 0, 16, 0)
        t_layout.setSpacing(8)

        self.close_btn = QPushButton(toolbar)
        self.close_btn.setFixedSize(36, 36)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.close_btn.setToolTip("Close editor")
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 10px;
            }}
            QPushButton:hover {{
                background: {CARD_HOVER};
                border-color: {BORDER_COLOR};
            }}
            QPushButton:focus {{ border-color: #2563EB; }}
        """)
        self.close_btn.clicked.connect(lambda: self.close_requested.emit())
        close_icon = VectorIcon("phosphor:light:x", color=TEXT_SEC, size=17, parent=self.close_btn)
        close_layout = QHBoxLayout(self.close_btn)
        close_layout.setContentsMargins(0, 0, 0, 0)
        close_layout.addWidget(close_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        t_layout.addWidget(self.close_btn)

        self.file_icon = VectorIcon(
            "phosphor:light:file-text", color=TEXT_SEC, size=19, parent=toolbar
        )
        t_layout.addWidget(self.file_icon)

        file_copy = QVBoxLayout()
        file_copy.setContentsMargins(0, 0, 0, 0)
        file_copy.setSpacing(1)
        self.file_context_lbl = QLabel("INI CONFIGURATION  ·  READ ONLY", toolbar)
        self.file_context_lbl.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 9px; font-weight: 800; "
            "letter-spacing: 0.6px; border: none; background: transparent;"
        )
        self.file_lbl = QLabel("SELECT_A_FILE.INI", toolbar)
        self.file_lbl.setMaximumWidth(142)
        self.file_lbl.setStyleSheet(
            f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 800; "
            "border: none; background: transparent;"
        )
        file_copy.addWidget(self.file_context_lbl)
        file_copy.addWidget(self.file_lbl)
        t_layout.addLayout(file_copy)
        t_layout.addStretch()

        self.edit_btn = QPushButton(toolbar)
        self.edit_btn.setFixedSize(96, 38)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.edit_btn_layout = QHBoxLayout(self.edit_btn)
        self.edit_btn_layout.setContentsMargins(10, 0, 10, 0)
        self.edit_btn_layout.setSpacing(6)
        self.edit_icon = VectorIcon(
            "phosphor:light:pencil-simple", color=TEXT_SEC, size=15, parent=self.edit_btn
        )
        self.edit_lbl = QLabel("EDIT", self.edit_btn)
        self.edit_lbl.setStyleSheet(
            "color: inherit; font-size: 10px; font-weight: 800; border: none; background: transparent;"
        )
        self.edit_btn_layout.addWidget(self.edit_icon)
        self.edit_btn_layout.addWidget(self.edit_lbl)
        t_layout.addWidget(self.edit_btn)

        self.save_btn = QPushButton(toolbar)
        self.save_btn.setFixedSize(82, 38)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.save_btn_layout = QHBoxLayout(self.save_btn)
        self.save_btn_layout.setContentsMargins(10, 0, 10, 0)
        self.save_btn_layout.setSpacing(6)
        self.save_icon = VectorIcon(
            "phosphor:light:floppy-disk", color="#94A3B8", size=15, parent=self.save_btn
        )
        self.save_lbl = QLabel("SAVE", self.save_btn)
        self.save_lbl.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: 800; border: none; background: transparent;"
        )
        self.save_btn_layout.addWidget(self.save_icon)
        self.save_btn_layout.addWidget(self.save_lbl)
        t_layout.addWidget(self.save_btn)
        layout.addWidget(toolbar)

        body_wrap = QWidget(self)
        body_wrap.setObjectName("iniBody")
        body_wrap.setStyleSheet("QWidget#iniBody { background: #F8FAFC; border: none; }")
        body_layout = QVBoxLayout(body_wrap)
        body_layout.setContentsMargins(16, 16, 16, 12)
        body_layout.setSpacing(0)

        self.editor_frame = QFrame(body_wrap)
        self.editor_frame.setObjectName("editorShell")
        self.editor_frame.setStyleSheet("""
            QFrame#editorShell {
                background: #111827;
                border: 1px solid #263449;
                border-radius: 14px;
            }
        """)
        e_layout = QVBoxLayout(self.editor_frame)
        e_layout.setContentsMargins(0, 0, 0, 0)
        e_layout.setSpacing(0)

        editor_toolbar = QFrame(self.editor_frame)
        editor_toolbar.setObjectName("codeToolbar")
        editor_toolbar.setFixedHeight(42)
        editor_toolbar.setStyleSheet("""
            QFrame#codeToolbar {
                background: #0B1220;
                border: none;
                border-bottom: 1px solid #263449;
                border-top-left-radius: 14px;
                border-top-right-radius: 14px;
            }
        """)
        et_layout = QHBoxLayout(editor_toolbar)
        et_layout.setContentsMargins(14, 0, 14, 0)
        et_layout.setSpacing(8)
        section_rail = QFrame(editor_toolbar)
        section_rail.setFixedSize(3, 18)
        section_rail.setStyleSheet("background: #EF4444; border: none; border-radius: 1px;")
        et_layout.addWidget(section_rail)
        editor_title = QLabel("CONFIGURATION", editor_toolbar)
        editor_title.setStyleSheet(
            "color: #E5E7EB; font-size: 10px; font-weight: 800; "
            "letter-spacing: 0.7px; border: none; background: transparent;"
        )
        et_layout.addWidget(editor_title)
        et_layout.addStretch()
        self.editor_mode_lbl = QLabel("READ ONLY", editor_toolbar)
        self.editor_mode_lbl.setStyleSheet(
            "color: #93C5FD; background: #14213A; border: 1px solid #24466F; "
            "border-radius: 6px; padding: 3px 7px; font-size: 9px; font-weight: 800;"
        )
        et_layout.addWidget(self.editor_mode_lbl)
        e_layout.addWidget(editor_toolbar)

        self.editor = CodeEditor(self.editor_frame)
        self.editor.setReadOnly(True)
        self.editor.textChanged.connect(self._on_text_changed)
        e_layout.addWidget(self.editor)
        body_layout.addWidget(self.editor_frame)
        layout.addWidget(body_wrap, 1)

        self.footer = EditorFooter(self)
        layout.addWidget(self.footer)

        self.is_editing = False
        self.original_content = ""
        self.edit_btn.clicked.connect(self._toggle_edit)
        self.save_btn.clicked.connect(self._on_save_clicked)
        self._apply_edit_state()
    def _on_text_changed(self):
        # Update lines count on edit
        lines = self.editor.blockCount()
        self.footer.update_lines(lines)
        if self.is_editing:
            self.footer.mark_saved(False)

    def _on_save_clicked(self):
        content = self.editor.toPlainText()
        self.original_content = content
        self.is_editing = False
        self._apply_edit_state()
        self.save_requested.emit(content)

    def load_content(self, title, content):
        display_title = title.upper()
        if not display_title.endswith(".INI"):
            display_title += ".INI"
        self.file_lbl.setToolTip(display_title)
        self.file_lbl.setText(
            self.file_lbl.fontMetrics().elidedText(
                display_title, Qt.TextElideMode.ElideMiddle, 142
            )
        )
        self.original_content = content
        self.editor.setPlainText(content)
        self.is_editing = False
        self._apply_edit_state()
        self.footer.update_lines(self.editor.blockCount())
        self.footer.mark_saved(True)

    def _toggle_edit(self, force_read_only=False):
        if force_read_only:
            self.is_editing = False
        elif self.is_editing:
            self.is_editing = False
            self.editor.blockSignals(True)
            self.editor.setPlainText(self.original_content)
            self.editor.blockSignals(False)
            self.footer.update_lines(self.editor.blockCount())
            self.footer.mark_saved(True)
        else:
            self.is_editing = True
        self._apply_edit_state()

    def _apply_edit_state(self):
        self.editor.setReadOnly(not self.is_editing)
        self.editor.highlight_current_line()
        self.save_btn.setEnabled(self.is_editing)

        if self.is_editing:
            self.file_context_lbl.setText("INI CONFIGURATION  ·  EDITING")
            self.editor_mode_lbl.setText("EDIT MODE")
            self.editor_mode_lbl.setStyleSheet(
                "color: #FBBF24; background: #332611; border: 1px solid #854D0E; "
                "border-radius: 6px; padding: 3px 7px; font-size: 9px; font-weight: 800;"
            )
            self.edit_lbl.setText("CANCEL")
            self.edit_icon.set_color("#DC2626")
            self.edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme_color("#FEF2F2")};
                    border: 1px solid {theme_color("#FCA5A5")};
                    color: #DC2626;
                    border-radius: 10px;
                }}
                QPushButton:hover {{ background: {theme_color("#FEE2E2")}; }}
                QPushButton:focus {{ border-color: #DC2626; }}
            """)
            self.save_icon.set_color("#FFFFFF")
            self.save_lbl.setStyleSheet(
                "color: #FFFFFF; font-size: 10px; font-weight: 800; "
                "border: none; background: transparent;"
            )
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background: #059669;
                    border: 1px solid #059669;
                    border-radius: 10px;
                }
                QPushButton:hover { background: #047857; border-color: #047857; }
                QPushButton:focus { border-color: #6EE7B7; }
            """)
            self.editor.setFocus()
        else:
            self.file_context_lbl.setText("INI CONFIGURATION  ·  READ ONLY")
            self.editor_mode_lbl.setText("READ ONLY")
            self.editor_mode_lbl.setStyleSheet(
                "color: #93C5FD; background: #14213A; border: 1px solid #24466F; "
                "border-radius: 6px; padding: 3px 7px; font-size: 9px; font-weight: 800;"
            )
            self.edit_lbl.setText("EDIT")
            self.edit_icon.set_color(TEXT_SEC)
            self.edit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {theme_color("#FFFFFF")};
                    border: 1px solid {theme_color(BORDER_COLOR)};
                    color: {theme_color(TEXT_SEC)};
                    border-radius: 10px;
                }}
                QPushButton:hover {{
                    background: {theme_color(CARD_HOVER)};
                    color: {theme_color(TEXT_MAIN)};
                    border-color: {theme_color("#CBD5E1")};
                }}
                QPushButton:focus {{ border-color: #2563EB; }}
            """)
            self.save_icon.set_color("#94A3B8")
            self.save_lbl.setStyleSheet(
                "color: #94A3B8; font-size: 10px; font-weight: 800; "
                "border: none; background: transparent;"
            )
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 10px;
                }
            """)
