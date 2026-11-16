# rk7_pro/components/script_vault_page.py
import os
import subprocess
from pathlib import Path
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QFrame, QScrollArea, QPlainTextEdit, QFileDialog, QMessageBox,
    QInputDialog, QApplication, QTextEdit
)
from PySide6.QtGui import QFont, QColor, QPainter, QTextFormat
from PySide6.QtCore import Qt, Signal as pyqtSignal, QTimer, QRect, QSize

from rk7_pro.theme import (
    APP_BG, BRAND_RED, BRAND_RED_DARK, TEXT_MAIN, TEXT_SEC,
    TEXT_MUTED, BORDER_COLOR, CARD_HOVER, SUCCESS, FONT_FAMILY, FONT_MONO, EDITOR_BG
)
from rk7_pro.components.icons import VectorIcon
from rk7_pro.components.code_highlighter import UniversalScriptHighlighter
from rk7_pro.core.script_repository import ScriptRepository, ScriptSnippet


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self.editor.lineNumberAreaPaintEvent(event)


class BalancedCodeEditor(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.line_number_area = LineNumberArea(self)

        self.blockCountChanged.connect(self.update_line_number_area_width)
        self.updateRequest.connect(self.update_line_number_area)
        self.cursorPositionChanged.connect(self.highlight_current_line)
        self.update_line_number_area_width(0)

        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #FAFAFC;
                color: #0F172A;
                font-family: 'Consolas', 'JetBrains Mono', monospace;
                font-size: 13px;
                line-height: 1.5;
                border: none;
                selection-background-color: #BFDBFE;
                selection-color: #1E3A8A;
            }
        """)
        self.document().setDocumentMargin(12)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self.highlight_current_line()

    def line_number_area_width(self):
        digits = 1
        m = max(1, self.blockCount())
        while m >= 10:
            m /= 10
            digits += 1
        space = 24 + self.fontMetrics().horizontalAdvance("9") * digits
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
            line_color = QColor("#F1F5F9")
            selection.format.setBackground(line_color)
            selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
            selection.cursor = self.textCursor()
            selection.cursor.clearSelection()
            extra_selections.append(selection)
        self.setExtraSelections(extra_selections)

    def lineNumberAreaPaintEvent(self, event):
        painter = QPainter(self.line_number_area)
        painter.fillRect(event.rect(), QColor("#F8FAFC"))
        painter.setPen(QColor("#E2E8F0"))
        painter.drawLine(event.rect().topRight(), event.rect().bottomRight())

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                number = str(block_number + 1)
                painter.setPen(QColor("#94A3B8"))
                painter.setFont(self.font())
                painter.drawText(
                    0, top, self.line_number_area.width() - 8, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, number
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1


class CleanScriptCard(QFrame):
    clicked = pyqtSignal(object)
    favorite_toggled = pyqtSignal(object)

    def __init__(self, snippet: ScriptSnippet, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self.snippet = snippet
        self.is_selected = is_selected
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._setup_ui()
        self.update_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(5)

        # Top row: Icon + Title + Star
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self.icon_box = QFrame(self)
        self.icon_box.setFixedSize(32, 32)
        ib_layout = QVBoxLayout(self.icon_box)
        ib_layout.setContentsMargins(0, 0, 0, 0)
        icon_name = "database" if self.snippet.file_type == "SQL" else ("terminal" if self.snippet.file_type in ("Batch", "PowerShell") else "file")
        self.icon_widget = VectorIcon(icon_name, color="#2563EB", size=16, parent=self.icon_box)
        ib_layout.addWidget(self.icon_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        top_row.addWidget(self.icon_box)

        # Title Label with clean truncation and tooltip
        clean_title = self.snippet.title.replace("\n", " ").strip()
        display_title = clean_title if len(clean_title) <= 50 else (clean_title[:47] + "...")
        self.title_lbl = QLabel(display_title, self)
        self.title_lbl.setToolTip(clean_title)
        self.title_lbl.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 800; border: none; background: transparent;")
        top_row.addWidget(self.title_lbl, stretch=1)

        self.btn_fav = QPushButton(self)
        self.btn_fav.setFixedSize(24, 24)
        self.btn_fav.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fav.setStyleSheet("background: transparent; border: none;")
        self._update_star_icon()
        self.btn_fav.clicked.connect(self._on_fav_clicked)
        top_row.addWidget(self.btn_fav)

        layout.addLayout(top_row)

        # Description / Snippet line
        raw_desc = (self.snippet.description or self.snippet.preview_snippet or "Không có mô tả...").replace("\n", " ").strip()
        display_desc = raw_desc if len(raw_desc) <= 60 else (raw_desc[:57] + "...")
        self.desc_lbl = QLabel(display_desc, self)
        self.desc_lbl.setToolTip(raw_desc)
        self.desc_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        layout.addWidget(self.desc_lbl)

        # Tags Row
        tags_row = QHBoxLayout()
        tags_row.setSpacing(5)
        display_tags = self.snippet.tags[:3] if self.snippet.tags else [f"#{self.snippet.file_type}"]
        for tag in display_tags:
            tag_badge = QLabel(tag, self)
            tag_badge.setStyleSheet("""
                QLabel {
                    background-color: #F1F5F9;
                    color: #475569;
                    border: 1px solid #E2E8F0;
                    border-radius: 4px;
                    font-size: 9px;
                    font-weight: 700;
                    padding: 1px 5px;
                }
            """)
            tags_row.addWidget(tag_badge)

        if len(self.snippet.tags) > 3:
            more_badge = QLabel(f"+{len(self.snippet.tags) - 3}", self)
            more_badge.setStyleSheet("color: #94A3B8; font-size: 9px; font-weight: 700;")
            tags_row.addWidget(more_badge)

        tags_row.addStretch()
        layout.addLayout(tags_row)

    def _update_star_icon(self):
        star_color = "#F59E0B" if self.snippet.is_favorite else "#CBD5E1"
        self.btn_fav.setText("★" if self.snippet.is_favorite else "☆")
        self.btn_fav.setStyleSheet(f"color: {star_color}; font-size: 14px; background: transparent; border: none;")

    def _on_fav_clicked(self):
        self.favorite_toggled.emit(self.snippet)
        self._update_star_icon()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.update_style()

    def update_style(self):
        if self.is_selected:
            self.icon_box.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 6px;")
            self.icon_widget.set_color("#2563EB")
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: #FFFFFF;
                    border: 1.5px solid {BRAND_RED};
                    border-radius: 10px;
                }}
            """)
        else:
            self.icon_box.setStyleSheet("background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px;")
            self.icon_widget.set_color("#64748B")
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: #FFFFFF;
                    border: 1px solid {BORDER_COLOR};
                    border-radius: 10px;
                }}
                QFrame:hover {{
                    background-color: {CARD_HOVER};
                    border-color: #CBD5E1;
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.snippet)
        super().mousePressEvent(event)


class ScriptVaultPage(QWidget):
    def __init__(self, vault_path: str = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background-color: {APP_BG};")

        if not vault_path:
            vault_path = os.path.join(os.path.expanduser("~"), "RK7_Script_Vault")

        self.repository = ScriptRepository(vault_path)
        self.current_snippet = None
        self.nav_filter = "all"
        self.cards = []

        self._setup_ui()
        self.reload_scripts()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 1. Top Header
        header = self._build_header()
        root.addWidget(header)

        # 2. Balanced 2-Column Split Layout
        split_layout = QHBoxLayout()
        split_layout.setContentsMargins(24, 18, 24, 20)
        split_layout.setSpacing(20)

        # Left Column: Search + Quick Category Filter Pills + Script Cards (380px)
        left_col = self._build_left_panel()
        split_layout.addWidget(left_col)

        # Right Column: Main Workspace (Flexible, expands nicely)
        right_col = self._build_right_workspace()
        split_layout.addWidget(right_col, stretch=1)

        root.addLayout(split_layout)

    def _build_header(self) -> QFrame:
        header = QFrame(self)
        header.setFixedHeight(72)
        header.setStyleSheet(f"background: #FFFFFF; border-bottom: 1px solid {BORDER_COLOR};")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(28, 12, 28, 12)
        layout.setSpacing(16)

        rail = QFrame(header)
        rail.setFixedSize(4, 32)
        rail.setStyleSheet(f"background: {BRAND_RED}; border-radius: 2px; border: none;")
        layout.addWidget(rail)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("Thư Viện Script & SQL Vault", header)
        title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 18px; font-weight: 800; border: none;")
        self.subtitle = QLabel(f"Lưu trữ, tra cứu và thực thi script nội bộ | Thư mục: {self.repository.vault_dir}", header)
        self.subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none;")
        copy.addWidget(title)
        copy.addWidget(self.subtitle)
        layout.addLayout(copy)
        layout.addStretch()

        # Action Buttons
        self.btn_new = QPushButton("➕ TẠO SCRIPT MỚI", header)
        self.btn_new.setFixedHeight(36)
        self.btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_new.setStyleSheet(f"""
            QPushButton {{
                background: {BRAND_RED};
                color: #FFFFFF;
                border-radius: 8px;
                padding: 0 16px;
                font-weight: 800;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {BRAND_RED_DARK}; }}
        """)
        self.btn_new.clicked.connect(self._on_new_script)
        layout.addWidget(self.btn_new)

        self.btn_import = QPushButton("📥 IMPORT SCRIPTS", header)
        self.btn_import.setFixedHeight(36)
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF;
                color: #2563EB;
                border: 1px solid #BFDBFE;
                border-radius: 8px;
                padding: 0 14px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #EFF6FF; border-color: #93C5FD; }}
        """)
        self.btn_import.clicked.connect(self._on_import_clicked)
        layout.addWidget(self.btn_import)

        self.btn_folder = QPushButton("📂 MỞ THƯ MỤC", header)
        self.btn_folder.setFixedHeight(36)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF;
                color: {TEXT_SEC};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 0 14px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: #CBD5E1; }}
        """)
        self.btn_folder.clicked.connect(self._open_vault_folder)
        layout.addWidget(self.btn_folder)

        self.btn_change_dir = QPushButton("⚙ ĐỔI THƯ MỤC", header)
        self.btn_change_dir.setFixedHeight(36)
        self.btn_change_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_dir.setStyleSheet(f"""
            QPushButton {{
                background: #FFFFFF;
                color: {TEXT_SEC};
                border: 1px solid {BORDER_COLOR};
                border-radius: 8px;
                padding: 0 14px;
                font-weight: 700;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {CARD_HOVER}; border-color: #CBD5E1; }}
        """)
        self.btn_change_dir.clicked.connect(self._change_vault_folder)
        layout.addWidget(self.btn_change_dir)

        return header

    def _build_left_panel(self) -> QWidget:
        container = QWidget(self)
        container.setFixedWidth(380)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        # 1. Search Box
        search_wrap = QFrame(container)
        search_wrap.setFixedHeight(42)
        search_wrap.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border: 1px solid {BORDER_COLOR};
                border-radius: 10px;
            }}
            QFrame:focus-within {{
                border: 1.5px solid {BRAND_RED};
            }}
        """)
        search_row = QHBoxLayout(search_wrap)
        search_row.setContentsMargins(12, 0, 12, 0)
        search_row.setSpacing(8)

        search_icon = VectorIcon("search", color=TEXT_MUTED, size=15, parent=search_wrap)
        search_row.addWidget(search_icon)

        self.search_input = QLineEdit(search_wrap)
        self.search_input.setPlaceholderText("Tìm theo tên, mô tả hoặc tag (#sql)...")
        self.search_input.setStyleSheet("border: none; background: transparent; font-size: 12px; color: " + TEXT_MAIN + ";")
        self.search_input.textChanged.connect(self._on_search_changed)
        search_row.addWidget(self.search_input)
        layout.addWidget(search_wrap)

        # 2. Filter Pills Segment
        filter_wrap = QFrame(container)
        filter_wrap.setFixedHeight(34)
        filter_wrap.setStyleSheet("background: #ECEFF4; border-radius: 8px; border: none;")
        filter_row = QHBoxLayout(filter_wrap)
        filter_row.setContentsMargins(3, 3, 3, 3)
        filter_row.setSpacing(2)

        self.filter_buttons = {}
        for fkey, flabel in [("all", "Tất cả"), ("favorite", "★ Yêu thích"), ("recent", "🕒 Gần đây"), ("sql", "SQL"), ("batch", "Batch/PS1")]:
            btn = QPushButton(flabel, filter_wrap)
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setChecked(fkey == "all")
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {TEXT_SEC};
                    border: none;
                    border-radius: 6px;
                    padding: 0 8px;
                    font-size: 10px;
                    font-weight: 700;
                }}
                QPushButton:hover {{ background: rgba(255, 255, 255, 0.5); }}
                QPushButton:checked {{
                    background: #FFFFFF;
                    color: {TEXT_MAIN};
                    font-weight: 800;
                }}
            """)
            btn.clicked.connect(lambda checked=False, k=fkey: self._on_filter_clicked(k))
            self.filter_buttons[fkey] = btn
            filter_row.addWidget(btn)

        layout.addWidget(filter_wrap)

        # 3. Script Cards Scroll
        self.scroll = QScrollArea(container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                border: none;
                background: transparent;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #CBD5E1;
                border-radius: 3px;
                min-height: 24px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94A3B8;
            }
        """)

        self.list_container = QWidget(self.scroll)
        self.list_container.setStyleSheet("background: transparent;")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 0, 4, 16)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()

        self.scroll.setWidget(self.list_container)
        layout.addWidget(self.scroll, stretch=1)

        # 4. Status Counter
        self.count_lbl = QLabel("0 scripts loaded", container)
        self.count_lbl.setFixedHeight(22)
        self.count_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-weight: 600; padding: 2px 4px;")
        layout.addWidget(self.count_lbl)

        return container

    def _build_right_workspace(self) -> QWidget:
        container = QFrame(self)
        container.setStyleSheet(f"""
            QFrame#rightPanel {{
                background: #FFFFFF;
                border: 1px solid {BORDER_COLOR};
                border-radius: 12px;
            }}
        """)
        container.setObjectName("rightPanel")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 1. Top Header Row: Title + Status + Action Buttons
        top_bar = QFrame(container)
        top_bar.setFixedHeight(64)
        top_bar.setStyleSheet(f"""
            QFrame {{
                background: #FFFFFF;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
                border-bottom: 1px solid {BORDER_COLOR};
            }}
        """)
        tb_layout = QHBoxLayout(top_bar)
        tb_layout.setContentsMargins(20, 10, 20, 10)
        tb_layout.setSpacing(12)

        icon_edit = VectorIcon("file", color=BRAND_RED, size=18, parent=top_bar)
        tb_layout.addWidget(icon_edit)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        
        # Inline Editable Title
        self.title_input = QLineEdit(top_bar)
        self.title_input.setPlaceholderText("Nhập tiêu đề script tại đây...")
        self.title_input.setStyleSheet(f"""
            QLineEdit {{
                color: {TEXT_MAIN};
                font-size: 15px;
                font-weight: 800;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 2px 6px;
                background: transparent;
            }}
            QLineEdit:hover {{
                border: 1px solid #CBD5E1;
                background: #F8FAFC;
            }}
            QLineEdit:focus {{
                border: 1.5px solid {BRAND_RED};
                background: #FFFFFF;
            }}
        """)
        self.title_input.editingFinished.connect(self._on_title_edited)
        title_box.addWidget(self.title_input)

        self.script_status_lbl = QLabel("● Chưa có thay đổi", top_bar)
        self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")
        title_box.addWidget(self.script_status_lbl)
        tb_layout.addLayout(title_box, stretch=1)

        # Action Buttons on Top Bar
        self.btn_copy = QPushButton("📋 Sao chép mã", top_bar)
        self.btn_copy.setFixedHeight(34)
        self.btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_copy.setStyleSheet("""
            QPushButton {{
                background: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 7px;
                padding: 0 14px;
                font-weight: 800;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #1D4ED8; }}
        """)
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        tb_layout.addWidget(self.btn_copy)

        self.btn_run = QPushButton("▶ Chạy", top_bar)
        self.btn_run.setFixedHeight(34)
        self.btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_run.setStyleSheet("""
            QPushButton {{
                background: #059669;
                color: #FFFFFF;
                border: none;
                border-radius: 7px;
                padding: 0 14px;
                font-weight: 800;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #047857; }}
        """)
        self.btn_run.clicked.connect(self._run_script)
        tb_layout.addWidget(self.btn_run)

        self.btn_save = QPushButton("💾 Lưu", top_bar)
        self.btn_save.setFixedHeight(34)
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.setStyleSheet("""
            QPushButton {{
                background: #142033;
                color: #FFFFFF;
                border: none;
                border-radius: 7px;
                padding: 0 14px;
                font-weight: 800;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #273549; }}
        """)
        self.btn_save.clicked.connect(self._save_script)
        tb_layout.addWidget(self.btn_save)

        self.btn_delete = QPushButton("🗑", top_bar)
        self.btn_delete.setFixedSize(34, 34)
        self.btn_delete.setToolTip("Xóa script này")
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setStyleSheet(f"""
            QPushButton {{
                background: #FEF2F2;
                color: {BRAND_RED};
                border: 1px solid #FECACA;
                border-radius: 7px;
                font-weight: 800;
            }}
            QPushButton:hover {{ background: #FEE2E2; }}
        """)
        self.btn_delete.clicked.connect(self._delete_current_script)
        tb_layout.addWidget(self.btn_delete)

        layout.addWidget(top_bar)

        # 2. Direct Inline Description & Tags Bar (Trực quan, sửa trực tiếp không cần popup)
        meta_panel = QFrame(container)
        meta_panel.setStyleSheet("""
            QFrame {
                background: #F8FAFC;
                border-bottom: 1px solid #E2E8F0;
            }
        """)
        mp_layout = QVBoxLayout(meta_panel)
        mp_layout.setContentsMargins(18, 8, 18, 8)
        mp_layout.setSpacing(6)

        # Row 1: Description Input (Mô tả trực quan)
        desc_row = QHBoxLayout()
        desc_row.setSpacing(8)

        lbl_desc_icon = QLabel("💡 Mô tả:", meta_panel)
        lbl_desc_icon.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        desc_row.addWidget(lbl_desc_icon)

        self.desc_input = QLineEdit(meta_panel)
        self.desc_input.setPlaceholderText("Nhập mô tả / hướng dẫn nhanh cho script này tại đây...")
        self.desc_input.setFixedHeight(28)
        self.desc_input.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                color: #1E293B;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1.5px solid #2563EB;
            }
        """)
        self.desc_input.editingFinished.connect(self._on_desc_edited)
        desc_row.addWidget(self.desc_input, stretch=1)
        mp_layout.addLayout(desc_row)

        # Row 2: Tags Input & Badges (Nhập tag trực tiếp)
        tags_row = QHBoxLayout()
        tags_row.setSpacing(8)

        lbl_tag_icon = QLabel("🏷 Nhóm thẻ:", meta_panel)
        lbl_tag_icon.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: 800; border: none; background: transparent;")
        tags_row.addWidget(lbl_tag_icon)

        self.tags_input = QLineEdit(meta_panel)
        self.tags_input.setPlaceholderText("Nhập thẻ tag (cách nhau bởi dấu phẩy, vd: #SQL, #CHECK_DATA, #RK7)...")
        self.tags_input.setFixedHeight(28)
        self.tags_input.setStyleSheet("""
            QLineEdit {
                background: #FFFFFF;
                color: #1D4ED8;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: 700;
            }
            QLineEdit:focus {
                border: 1.5px solid #2563EB;
            }
        """)
        self.tags_input.editingFinished.connect(self._on_tags_edited)
        tags_row.addWidget(self.tags_input, stretch=1)

        self.file_info_lbl = QLabel("0 KB • file", meta_panel)
        self.file_info_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; border: none; background: transparent;")
        tags_row.addWidget(self.file_info_lbl)

        mp_layout.addLayout(tags_row)
        layout.addWidget(meta_panel)

        # 3. Clean Code Editor with Line Numbers
        self.editor = BalancedCodeEditor(container)
        self.highlighter = UniversalScriptHighlighter(self.editor.document(), "SQL")
        self.editor.textChanged.connect(self._on_editor_modified)
        layout.addWidget(self.editor, stretch=1)

        # 4. Description & Notes Footer (collapsible/clean view)
        self.guide_bar = QFrame(container)
        self.guide_bar.setFixedHeight(36)
        self.guide_bar.setStyleSheet("background: #F8FAFC; border-top: 1px solid #E2E8F0; border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;")
        gb_layout = QHBoxLayout(self.guide_bar)
        gb_layout.setContentsMargins(18, 0, 18, 0)
        gb_layout.setSpacing(10)

        gb_icon = QLabel("💡", self.guide_bar)
        gb_layout.addWidget(gb_icon)

        self.guide_lbl = QLabel("Mô tả: Chưa có ghi chú hướng dẫn.", self.guide_bar)
        self.guide_lbl.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; border: none; background: transparent;")
        gb_layout.addWidget(self.guide_lbl, stretch=1)

        self.footer_lines_lbl = QLabel("0 LINES", self.guide_bar)
        self.footer_lines_lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; border: none; background: transparent;")
        gb_layout.addWidget(self.footer_lines_lbl)

        layout.addWidget(self.guide_bar)

        return container

    def _on_editor_modified(self):
        if self.current_snippet and self.editor.toPlainText() != self.current_snippet.content:
            self.script_status_lbl.setText("● Đã sửa (chưa lưu)")
            self.script_status_lbl.setStyleSheet("color: #F59E0B; font-size: 11px; font-weight: 700;")
        else:
            self.script_status_lbl.setText("● Chưa có thay đổi")
            self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")

    def reload_scripts(self):
        self.repository.scan()
        self.subtitle.setText(f"Lưu trữ, tra cứu và thực thi script nội bộ | Thư mục: {self.repository.vault_dir}")
        self._render_script_list()

    def _render_script_list(self):
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()

        query = self.search_input.text()
        nav_filter = self.nav_filter

        type_filter = None
        if nav_filter in ("sql", "batch"):
            type_filter = "SQL" if nav_filter == "sql" else "BATCH"
            nav_filter = "all"

        filtered = self.repository.filter(query=query, nav_filter=nav_filter)
        if type_filter:
            if type_filter == "BATCH":
                filtered = [s for s in filtered if s.suffix in (".bat", ".cmd", ".ps1")]
            else:
                filtered = [s for s in filtered if s.file_type.upper() == type_filter]

        self.count_lbl.setText(f"Hiển thị {len(filtered)} / {len(self.repository.snippets)} scripts")

        for snippet in filtered:
            is_sel = (self.current_snippet and self.current_snippet.file_path == snippet.file_path)
            card = CleanScriptCard(snippet, is_selected=is_sel, parent=self.list_container)
            card.clicked.connect(self._on_snippet_selected)
            card.favorite_toggled.connect(self._on_favorite_toggled)
            self.cards.append(card)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)

        if filtered:
            target = next((s for s in filtered if self.current_snippet and s.file_path == self.current_snippet.file_path), filtered[0])
            self._on_snippet_selected(target)

    def _on_filter_clicked(self, fkey: str):
        self.nav_filter = fkey
        for k, btn in self.filter_buttons.items():
            btn.setChecked(k == fkey)
        self._render_script_list()

    def _on_favorite_toggled(self, snippet: ScriptSnippet):
        self.repository.toggle_favorite(snippet)
        if self.nav_filter == "favorite":
            self._render_script_list()

    def _on_search_changed(self, text: str):
        self._render_script_list()

    def _on_snippet_selected(self, snippet: ScriptSnippet):
        self.current_snippet = snippet
        self.repository.record_viewed(snippet)

        for card in self.cards:
            card.set_selected(card.snippet.file_path == snippet.file_path)

        self.title_input.blockSignals(True)
        self.title_input.setText(snippet.title)
        self.title_input.blockSignals(False)

        self.script_status_lbl.setText("● Chưa có thay đổi")
        self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")

        size_kb = round(snippet.size_bytes / 1024, 1)
        self.file_info_lbl.setText(f"{size_kb} KB • {snippet.filename}")

        self.desc_input.blockSignals(True)
        self.desc_input.setText(snippet.description or "")
        self.desc_input.blockSignals(False)

        self.tags_input.blockSignals(True)
        self.tags_input.setText(", ".join(snippet.tags) if snippet.tags else "#SQL")
        self.tags_input.blockSignals(False)

        # Update syntax & editor text
        self.highlighter.set_language(snippet.file_type)
        content = snippet.load_full_content()
        self.editor.blockSignals(True)
        self.editor.setPlainText(content)
        self.editor.blockSignals(False)

        self.footer_lines_lbl.setText(f"{snippet.line_count} LINES")

        # Run button visibility
        self.btn_run.setVisible(snippet.suffix in (".bat", ".cmd", ".ps1", ".py"))

    def _on_desc_edited(self):
        if not self.current_snippet:
            return
        new_desc = self.desc_input.text().strip()
        if new_desc != self.current_snippet.description:
            self.current_snippet.description = new_desc
            self.repository.update_snippet_meta(
                self.current_snippet, self.current_snippet.title, new_desc, self.current_snippet.tags
            )
            self._render_script_list()
            self.script_status_lbl.setText("✓ Đã cập nhật mô tả!")
            self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")

    def _on_tags_edited(self):
        if not self.current_snippet:
            return
        tags_raw = self.tags_input.text()
        new_tags = [t.strip() if t.strip().startswith("#") else f"#{t.strip()}" for t in tags_raw.split(",") if t.strip()]
        if not new_tags:
            new_tags = ["#SQL" if self.current_snippet.file_type == "SQL" else "#SCRIPT"]
        self.current_snippet.tags = new_tags
        self.repository.update_snippet_meta(
            self.current_snippet, self.current_snippet.title, self.current_snippet.description, new_tags
        )
        self._render_script_list()
        self.script_status_lbl.setText("✓ Đã cập nhật thẻ tags!")
        self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")

    def _on_title_edited(self):
        if not self.current_snippet:
            return
        new_title = self.title_input.text().strip()
        if new_title and new_title != self.current_snippet.title:
            self.repository.rename_snippet(self.current_snippet, new_title)
            self._render_script_list()
            self.script_status_lbl.setText("✓ Đã cập nhật tiêu đề!")
            self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")

    def _copy_to_clipboard(self):
        text = self.editor.toPlainText()
        if not text:
            return
        QApplication.clipboard().setText(text)
        self.script_status_lbl.setText("✓ Đã sao chép vào Clipboard!")
        self.script_status_lbl.setStyleSheet("color: #2563EB; font-size: 11px; font-weight: 700;")
        QTimer.singleShot(2200, lambda: self.script_status_lbl.setText("● Chưa có thay đổi"))

    def _save_script(self):
        if not self.current_snippet:
            return
        text = self.editor.toPlainText()
        if self.current_snippet.save_content(text):
            self.highlighter.set_language(self.current_snippet.file_type)
            self.script_status_lbl.setText("✓ Đã lưu thay đổi!")
            self.script_status_lbl.setStyleSheet("color: #10B981; font-size: 11px; font-weight: 700;")
            self._render_script_list()
        else:
            QMessageBox.warning(self, "Lỗi", "Không thể ghi file!")

    def _run_script(self):
        if not self.current_snippet:
            return
        path = str(self.current_snippet.file_path)
        try:
            if self.current_snippet.suffix in (".bat", ".cmd"):
                subprocess.Popen(["cmd.exe", "/c", "start", "", path], shell=True)
            elif self.current_snippet.suffix == ".ps1":
                subprocess.Popen(["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", path])
            elif self.current_snippet.suffix == ".py":
                subprocess.Popen(["python", path], creationflags=subprocess.CREATE_NEW_CONSOLE)
            else:
                os.startfile(path)
            self.script_status_lbl.setText("✓ Đang chạy script...")
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể chạy script: {e}")

    def _on_new_script(self):
        # Automatically generate a unique script file name without blocking popups
        base_name = "Script_Moi"
        ext = ".sql"
        counter = 1
        candidate = f"{base_name}_{counter}{ext}"
        while (self.repository.vault_dir / candidate).exists():
            counter += 1
            candidate = f"{base_name}_{counter}{ext}"

        initial_code = "-- Viết câu lệnh SQL hoặc nội dung script tại đây...\n"
        snippet = self.repository.add_new_snippet(
            candidate, initial_code,
            title=f"SCRIPT MỚI #{counter}"
        )
        self.reload_scripts()
        self._on_snippet_selected(snippet)

        # Automatically focus editor and select all placeholder text
        self.editor.setFocus()
        self.editor.selectAll()
        self.script_status_lbl.setText("● Script mới (nhập nội dung và sửa tiêu đề ở trên)")
        self.script_status_lbl.setStyleSheet("color: #2563EB; font-size: 11px; font-weight: 700; border: none; background: transparent; padding-left: 6px;")

    def _delete_current_script(self):
        if not self.current_snippet:
            return
        reply = QMessageBox.question(
            self, "Xác nhận xóa",
            f"Bạn có chắc muốn xóa vĩnh viễn script:\n{self.current_snippet.title} ({self.current_snippet.filename})?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.repository.delete_snippet(self.current_snippet)
            self.current_snippet = None
            self.reload_scripts()

    def _on_edit_meta_dialog(self):
        if not self.current_snippet:
            return
        title, ok1 = QInputDialog.getText(self, "Tiêu đề Script", "Nhập tiêu đề hiển thị:", text=self.current_snippet.title)
        if not ok1:
            return
        tags_str, ok2 = QInputDialog.getText(self, "Từ khóa / Tags", "Nhập tags (cách nhau bởi dấu phẩy):", text=", ".join(self.current_snippet.tags))
        if not ok2:
            return
        desc, ok3 = QInputDialog.getMultiLineText(self, "Mô tả / Hướng dẫn", "Nhập hướng dẫn sử dụng:", text=self.current_snippet.description)
        if not ok3:
            return

        tags = [t.strip() if t.strip().startswith("#") else f"#{t.strip()}" for t in tags_str.split(",") if t.strip()]
        self.repository.update_snippet_meta(self.current_snippet, title.strip(), desc.strip(), tags)
        self._on_snippet_selected(self.current_snippet)
        self._render_script_list()

    def _open_vault_folder(self):
        os.startfile(str(self.repository.vault_dir))

    def _change_vault_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Chọn thư mục lưu trữ Script & SQL", str(self.repository.vault_dir)
        )
        if folder:
            self.repository.set_vault_dir(folder)
            self.reload_scripts()

    def _on_import_clicked(self):
        menu_box = QMessageBox(self)
        menu_box.setWindowTitle("Import Scripts vào Thư Viện")
        menu_box.setText("Chọn phương thức import:")
        btn_folder = menu_box.addButton("📁 Import cả thư mục", QMessageBox.ButtonRole.ActionRole)
        btn_files = menu_box.addButton("📄 Chọn các file lẻ", QMessageBox.ButtonRole.ActionRole)
        btn_cancel = menu_box.addButton("Hủy", QMessageBox.ButtonRole.RejectRole)
        menu_box.exec()

        if menu_box.clickedButton() == btn_folder:
            folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa script cần import")
            if folder:
                count = self.repository.import_from_folder(folder)
                self.reload_scripts()
                if count > 0:
                    QMessageBox.information(self, "Thành công", f"Đã import thành công {count} script vào thư viện!")
                else:
                    QMessageBox.warning(self, "Thông báo", "Không tìm thấy file script hợp lệ (.sql, .bat, .ps1, .py, .txt, .text) trong thư mục này.")

        elif menu_box.clickedButton() == btn_files:
            file_filter = "Script Files (*.sql *.bat *.cmd *.ps1 *.py *.sh *.json *.txt *.text *.ini);;All Files (*.*)"
            files, _ = QFileDialog.getOpenFileNames(self, "Chọn các file script cần import", "", file_filter)
            if files:
                count = self.repository.import_files(files)
                self.reload_scripts()
                if count > 0:
                    QMessageBox.information(self, "Thành công", f"Đã import thành công {count} file vào thư viện!")
                else:
                    QMessageBox.warning(self, "Thông báo", "Không thể copy các file đã chọn.")
