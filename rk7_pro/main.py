# rk7_pro/main.py
import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QHBoxLayout, QVBoxLayout, QWidget, QMessageBox, QStackedWidget, QLabel, QPushButton
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint


# Import Theme
from rk7_pro.theme import GLOBAL_QSS, APP_BG, TEXT_MUTED, BORDER_COLOR
from rk7_pro.theme_manager import set_dark_mode, apply_widget_theme
from rk7_pro.version import APP_VERSION

# Import Components
from rk7_pro.components.sidebar import SidebarNavigation
from rk7_pro.components.header import TopHeader
from rk7_pro.components.search_bar import SearchBar
from rk7_pro.components.settings_page import SettingsPage
from rk7_pro.components.script_vault_page import ScriptVaultPage
from rk7_pro.components.cluster_list import ClusterListPanel
from rk7_pro.components.editor import MainWorkspace as IniEditorPanel
from rk7_pro.components.customization_dialog import CustomizationDialog
from rk7_pro.core.shortcut_repository import ShortcutRepository
from rk7_pro.core.launch_service import ShortcutLaunchService
from rk7_pro.core.process_tracker import ProcessTrackingService

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RK7 PRO")
        self.setWindowIcon(QIcon("rk7_pro/assets/rk7_logo.png"))
        self.setMinimumSize(1024, 680)
        self.resize(1440, 860)
        
        # Initialize
        settings = self._load_settings()
        self.dark_mode = settings.get("theme", "light") == "dark"
        target_dir = settings.get("shortcut_root", r"C:UsersAdminOneDriveRK7Shortcut")
        if not Path(target_dir).exists():
            target_dir = str(Path.home() / "Desktop") # fallback
            
        self.repository = ShortcutRepository(target_dir)
        self.launch_service = ShortcutLaunchService(self.repository)
        self.process_tracker = ProcessTrackingService(self.repository)
        
        self.current_ini_path = None
        self.current_state_id = None
        self.current_mode = "launch"
        self.editor_visible = False
        self.drawer_width = 480
        self.view_mode = "grid"
        self._last_action_key = None
        self._last_action_at = 0.0

        # Search debounce timer
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self._exec_search)
        
        # --- Set theme state early before widgets instantiate ---
        import rk7_pro.theme_manager as tm
        tm._DARK_MODE = self.dark_mode

        # --- UI Build ---
        self._setup_ui(target_dir)
        self._connect_signals()
        self._set_dark_mode(self.dark_mode, persist=False)
        self._start_services()

    def _set_dark_mode(self, dark, persist=True):
        self.dark_mode = bool(dark)
        if self.header.theme_toggle.isChecked() != self.dark_mode:
            self.header.theme_toggle.set_dark(self.dark_mode, animate=False)
        set_dark_mode(self, self.dark_mode)
        if persist:
            self._save_setting("theme", "dark" if self.dark_mode else "light")
    def _start_services(self):
        self.repository.initialize()
        self.process_tracker.start()
        
    def _connect_signals(self):
        self.sidebar.module_changed.connect(self._on_module_changed)
        self.header.settings_requested.connect(lambda: self.sidebar._on_nav_click("SETTINGS"))
        self.header.theme_toggle.toggled.connect(self._set_dark_mode)
        self.all_filter_btn.clicked.connect(lambda: self._set_status_filter("all"))
        self.pinned_filter_btn.clicked.connect(lambda: self._set_status_filter("pinned"))
        self.running_filter_btn.clicked.connect(lambda: self._set_status_filter("running"))
        self.refresh_btn.clicked.connect(self._refresh_with_feedback)
        
        self.settings_page.source_changed.connect(self._on_source_changed)
        
        self.search_bar.input_field.textChanged.connect(self._on_search)
        self.search_bar.input_field.returnPressed.connect(self._on_search_enter)
        self.sidebar.btn_quick_search.clicked.connect(self.search_bar.input_field.setFocus)
        
        self.cluster_list.cluster_selected.connect(self._on_cluster_selected)
        self.cluster_list.pin_toggled.connect(self._on_pin_toggled)
        self.cluster_list.go_clicked.connect(self._on_cluster_go_clicked)
        self.cluster_list.customization_requested.connect(self._on_customization_requested)
        self.cluster_list.ini_clicked.connect(self._on_ini_clicked)
        self.cluster_list.folder_clicked.connect(self._on_folder_clicked)
        
        self.repository.store_ready.connect(self._refresh_ui)
        self.repository.state_changed.connect(self._on_state_changed)

    def _setup_ui(self, target_dir):
        from rk7_pro.theme import BORDER_COLOR

        central = QWidget(self)
        self.setCentralWidget(central)
        central.setStyleSheet(f"background-color: {APP_BG};")
        
        self.main_layout = QHBoxLayout(central)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # --- Column 1: Sidebar (Fixed Width 220px) ---
        self.sidebar = SidebarNavigation()
        self.main_layout.addWidget(self.sidebar)
        
        # --- Stack Container ---
        self.stack = QStackedWidget()
        
        # --- Page 0: Operational View (Cols 2 & 3 Combined) ---
        main_content_container = QWidget(self)
        main_content_layout = QVBoxLayout(main_content_container)
        main_content_layout.setContentsMargins(0, 0, 0, 0)
        main_content_layout.setSpacing(0)
        
        # --- Context header + operational toolbar ---
        top_section = QWidget(main_content_container)
        top_section.setFixedHeight(142)
        top_section.setStyleSheet(f"background: {APP_BG}; border: none;")
        top_layout = QVBoxLayout(top_section)
        top_layout.setContentsMargins(0, 0, 0, 10)
        top_layout.setSpacing(6)

        self.header = TopHeader()
        top_layout.addWidget(self.header)

        search_wrap = QWidget(top_section)
        search_wrap.setStyleSheet("background: transparent; border: none;")
        sw_layout = QHBoxLayout(search_wrap)
        sw_layout.setContentsMargins(28, 0, 28, 0)
        sw_layout.setSpacing(8)

        self.search_bar = SearchBar()
        sw_layout.addWidget(self.search_bar, stretch=1)

        from rk7_pro.components.icons import VectorIcon
        from rk7_pro.theme import CARD_HOVER, BORDER_COLOR, TEXT_SEC, BRAND_RED

        def create_filter_btn(label):
            button = QPushButton(label, search_wrap)
            button.setFixedHeight(40)
            button.setMinimumWidth(68)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setCheckable(True)
            button.setStyleSheet(f"""
                QPushButton {{
                    background: #13161C;
                    color: #94A3B8;
                    border: 1px solid #1E232D;
                    border-radius: 10px;
                    padding: 0 14px;
                    font-size: 11px;
                    font-weight: 700;
                }}
                QPushButton:hover {{ background: #181C24; border-color: #2D3748; color: #F8FAFC; }}
                QPushButton:checked {{
                    background: #F8FAFC;
                    color: #09090B;
                    border-color: #F8FAFC;
                    font-weight: 800;
                }}
                QPushButton:focus {{ border-color: #3B82F6; }}
            """)
            return button

        def create_toolbar_btn(icon_name, tooltip):
            button = QPushButton(search_wrap)
            button.setFixedSize(40, 40)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setToolTip(tooltip)
            button.setCheckable(icon_name in ("grid", "list"))
            button.setStyleSheet(f"""
                QPushButton {{
                    background: #13161C;
                    border: 1px solid #1E232D;
                    border-radius: 10px;
                }}
                QPushButton:hover {{ background: #181C24; border-color: #2D3748; }}
                QPushButton:focus {{ border-color: #3B82F6; }}
                QPushButton:checked {{ background: #1E293B; border-color: #3B82F6; }}
            """)
            button_layout = QHBoxLayout(button)
            button_layout.setContentsMargins(0, 0, 0, 0)
            button_layout.addWidget(
                VectorIcon(icon_name, color="#94A3B8", size=15, parent=button),
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
            return button

        self.all_filter_btn = create_filter_btn("ALL")
        self.pinned_filter_btn = create_filter_btn("PINNED")
        self.running_filter_btn = create_filter_btn("RUNNING")
        for btn in (self.all_filter_btn, self.pinned_filter_btn, self.running_filter_btn):
            btn.setProperty("_rk7_theme_static", True)
        self.all_filter_btn.setChecked(True)
        self.refresh_btn = create_toolbar_btn("refresh", "Reload shortcuts")
        self.refresh_btn.setProperty("_rk7_theme_static", True)
        self.refresh_btn.hide()
        sw_layout.addWidget(self.all_filter_btn)
        sw_layout.addWidget(self.pinned_filter_btn)
        sw_layout.addWidget(self.running_filter_btn)
        top_layout.addWidget(search_wrap)

        main_content_layout.addWidget(top_section)
        
        # --- Bottom Section (List + Editor) ---
        split_section = QWidget(self)
        split_layout = QHBoxLayout(split_section)
        split_layout.setContentsMargins(0, 0, 0, 0)
        split_layout.setSpacing(0)
        
        # --- Column 2: Cluster List ---
        col2_container = QWidget(split_section)
        # Make it expand dynamically, columns default to 3
        col2_layout = QVBoxLayout(col2_container)
        col2_layout.setContentsMargins(28, 20, 28, 0)
        col2_layout.setSpacing(16)
        
        self.cluster_list = ClusterListPanel()
        self.cluster_list.set_columns(2)
        col2_layout.addWidget(self.cluster_list)
        
        split_layout.addWidget(col2_container)
        
        self.split_section = split_section
        
        # Dim overlay widget
        self.dim_overlay = QWidget(split_section)
        self.dim_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 0.12); border: none;")
        self.dim_overlay.hide()
        self.dim_overlay.mousePressEvent = lambda event: self._hide_editor()
        
        self.editor_panel = IniEditorPanel(split_section)
        self.editor_panel.save_requested.connect(self._on_ini_save)
        self.editor_panel.close_requested.connect(self._hide_editor)
        self.editor_panel.hide()
        main_content_layout.addWidget(split_section)

        
        self.stack.addWidget(main_content_container)
        
        # --- Page 1: Settings View ---
        self.settings_page = SettingsPage(target_dir)
        self.stack.addWidget(self.settings_page)
        
        # --- Page 2: Web View (Ghi Issue) ---
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEnginePage
        
        # Create a dedicated persistent profile owned by MainWindow to keep it alive
        self.web_profile = QWebEngineProfile("rk7_web_profile", self)
        self.web_profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        
        self.web_view = QWebEngineView(self)
        self.web_page = QWebEnginePage(self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)
        self.web_view.setUrl("https://ghiissue.itspecialone.site/")
        
        # Web View Wrapper layout to add navigation controls
        self.web_container = QWidget(self)
        web_layout = QVBoxLayout(self.web_container)
        web_layout.setContentsMargins(0, 0, 0, 0)
        web_layout.setSpacing(0)
        
        # Web Navigation Bar (Toolbar)
        from rk7_pro.theme import SIDEBAR_BG, CARD_HOVER, BORDER_COLOR, TEXT_MAIN
        from rk7_pro.components.icons import VectorIcon
        from PySide6.QtWidgets import QFrame
        
        web_nav_bar = QWidget(self.web_container)
        web_nav_bar.setFixedHeight(58)
        web_nav_bar.setStyleSheet(f"background-color: {SIDEBAR_BG}; border-bottom: 1px solid {BORDER_COLOR};")
        
        nav_bar_layout = QHBoxLayout(web_nav_bar)
        nav_bar_layout.setContentsMargins(20, 0, 20, 0)
        nav_bar_layout.setSpacing(10)
        
        web_title = QLabel("ISSUE WORKSPACE", web_nav_bar)
        web_title.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 13px; font-weight: bold; letter-spacing: 0.5px;")
        nav_bar_layout.addWidget(web_title)
        
        # Vertical Separator
        sep = QFrame(web_nav_bar)
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet(f"color: {BORDER_COLOR}; max-height: 20px;")
        nav_bar_layout.addWidget(sep)
        
        def create_web_nav_btn(icon_name, text, tooltip, callback, is_danger=False):
            btn = QPushButton(web_nav_bar)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(tooltip)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            
            btn_layout = QHBoxLayout(btn)
            btn_layout.setContentsMargins(10, 0, 10, 0)
            btn_layout.setSpacing(6)
            
            icon = VectorIcon(icon_name, color=TEXT_MAIN, size=14, parent=btn)
            btn_layout.addWidget(icon, alignment=Qt.AlignmentFlag.AlignCenter)
            
            if text:
                lbl = QLabel(text, btn)
                lbl.setStyleSheet(f"color: {TEXT_MAIN}; font-size: 11px; font-weight: bold; background: transparent; letter-spacing: 0.3px;")
                btn_layout.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
                btn.setFixedHeight(34)
            else:
                btn.setFixedSize(34, 34)
                
            if is_danger:
                hover_bg = "rgba(239, 68, 68, 0.12)"
                hover_border = "rgba(239, 68, 68, 0.4)"
            else:
                hover_bg = CARD_HOVER
                hover_border = "rgba(239, 68, 68, 0.35)"
                
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgba(255, 255, 255, 0.03);
                    border: 1px solid {BORDER_COLOR};
                    border-radius: 10px;
                }}
                QPushButton:hover {{
                    background-color: {hover_bg};
                    border: 1px solid {hover_border};
                }}
            """)
            btn.clicked.connect(callback)
            return btn
            
        self.btn_web_back = create_web_nav_btn("arrow_left", "", "Go back", self.web_view.back)
        self.btn_web_forward = create_web_nav_btn("arrow_right", "", "Go forward", self.web_view.forward)
        self.btn_web_reload = create_web_nav_btn("refresh", "TẢI LẠI TRANG", "Reload page", self.web_view.reload)
        self.btn_web_clear = create_web_nav_btn("trash", "XÓA PHIÊN ĐĂNG NHẬP", "Clear cookies & cache to log out", self._clear_web_cache, is_danger=True)
        
        nav_bar_layout.addWidget(self.btn_web_back)
        nav_bar_layout.addWidget(self.btn_web_forward)
        nav_bar_layout.addWidget(self.btn_web_reload)
        nav_bar_layout.addWidget(self.btn_web_clear)
        
        nav_bar_layout.addStretch()
        
        web_layout.addWidget(web_nav_bar)
        web_layout.addWidget(self.web_view)
        
        self.stack.addWidget(self.web_container)
        
        # --- Page 3: Script & SQL Vault ---
        settings = self._load_settings()
        vault_dir = settings.get("script_vault_dir", str(Path.home() / "RK7_Script_Vault"))
        self.script_vault_page = ScriptVaultPage(vault_dir, self)
        self.stack.addWidget(self.script_vault_page)
        
        self.main_layout.addWidget(self.stack)
        
        # Setup animation
        self.editor_animation = QPropertyAnimation(self.editor_panel, b"geometry")
        self.editor_animation.setDuration(250)
        self.editor_animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.editor_animation.finished.connect(self._on_animation_finished)
        
        # Store layout references for mode switching
        self.col2_container = col2_container

    def _on_source_changed(self, new_path):
        if self.repository.update_root_folder(new_path):
            self._save_setting("shortcut_root", new_path)
            self._refresh_ui()
            self.settings_page.update_status(f"Loaded {len(self.repository.get_all())} shortcuts")
        else:
            self.settings_page.update_status(f"Invalid or missing folder: {new_path}", True)

    def _refresh_ui(self):
        states = self.repository.get_all()
        states.sort(key=lambda s: (not s.is_pinned, s.name.lower()))
        self.cluster_list.populate(states)
        self.header.set_metrics(
            len(states),
            sum(1 for state in states if state.is_running),
            sum(1 for state in states if state.is_pinned),
        )
        
        current_search = self.search_bar.input_field.text()
        if current_search:
            self.cluster_list.filter_cards(current_search)
        
        if states:
            # Silent selection on refresh/start (no animation/drawer trigger)
            first_id = states[0].id
            self.current_state_id = first_id
            self.cluster_list.select_card(first_id)
            state = self.repository.get_by_id(first_id)
            if state:
                ini_path = self._find_related_ini(state)
                if ini_path:
                    try:
                        with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        self.editor_panel.load_content(Path(ini_path).name, content)
                        self.current_ini_path = ini_path
                    except Exception as e:
                        self.editor_panel.load_content("ERROR", f"Could not read file: {e}")
                else:
                    self.editor_panel.load_content("NO INI FOUND", "No configuration file detected for this shortcut.")

        if self.dark_mode:
            apply_widget_theme(self.cluster_list, True)

    def _on_state_changed(self, state_id, state):
        self.cluster_list.update_state(state)
        states = self.repository.get_all()
        self.header.set_metrics(
            len(states),
            sum(1 for item in states if item.is_running),
            sum(1 for item in states if item.is_pinned),
        )
        if self.cluster_list._status_filter == "running":
            self.cluster_list.filter_cards(self.search_bar.input_field.text())


    def _on_search(self, text):
        self.search_timer.start(150) # 150ms debounce
        
    def _exec_search(self):
        text = self.search_bar.input_field.text()
        self.cluster_list.filter_cards(text)

    def _on_module_changed(self, module_name):
        contexts = {
            "LAUNCH": ("Shortcut Library", "Launch and monitor RK7 environments"),
            "SCRIPT VAULT": ("Script & SQL Vault", "Lưu trữ, xem trước và thực thi các đoạn mã SQL, batch, script"),
            "GHI ISSUE": ("Issue Workspace", "Work with the connected issue tool"),
            "SETTINGS": ("Settings", "Configure the shortcut source and application preferences"),
        }
        self.header.set_context(*contexts.get(module_name, contexts["LAUNCH"]))
        if module_name == "SETTINGS":
            self.stack.setCurrentIndex(1)
            # Update status text cleanly
            count = len(self.repository.get_all())
            self.settings_page.update_status(f"Current shortcut count: {count} | Connected")
        elif module_name == "GHI ISSUE":
            self.stack.setCurrentIndex(2)
        elif module_name == "SCRIPT VAULT":
            self.stack.setCurrentIndex(3)
            self.script_vault_page.reload_scripts()
        else:
            self.stack.setCurrentIndex(0)
            if module_name == "LAUNCH":
                self.current_mode = "launch"
                self.cluster_list.set_mode("launch")
                # Hide editor panel by default on entering Launch
                self._hide_editor()
                self._refresh_ui()


    def _accept_action(self, action, state_id, cooldown=0.8):
        now = time.monotonic()
        key = f"{action}:{state_id}"
        if self._last_action_key == key and now - self._last_action_at < cooldown:
            return False
        self._last_action_key = key
        self._last_action_at = now
        return True

    def _launch_shortcut_once(self, state_id):
        if not self._accept_action("launch", state_id, 1.0):
            return False
        return self.launch_service.launch(state_id)
    def _on_search_enter(self):
        self.search_timer.stop()
        self._exec_search()
        # Find the first visible shortcut in the search results
        for card in self.cluster_list.cards:
            if card.isVisible():
                self._launch_shortcut_once(card.state_id)
                return

    def _on_cluster_go_clicked(self, state_id):
        self._launch_shortcut_once(state_id)

    def _open_folder(self, state_id):
        state = self.repository.get_by_id(state_id)
        if not state:
            return
            
        folder = None
        if state.target_exe_path:
            p = Path(state.target_exe_path)
            if p.exists():
                if p.is_dir():
                    folder = str(p)
                else:
                    folder = str(p.parent)
        
        if not folder and state.working_directory and Path(state.working_directory).exists():
            folder = state.working_directory
            
        if folder:
            import os
            os.startfile(folder)
        else:
            QMessageBox.warning(self, "Error", f"Could not determine valid folder for {state.name}")
            
    def _on_cluster_selected(self, state_id):
        self.current_state_id = state_id
        self.cluster_list.select_card(state_id)
        self._launch_shortcut_once(state_id)

    def _on_ini_clicked(self, state_id):
        if not self._accept_action("ini", state_id):
            return
        self.current_state_id = state_id
        self.cluster_list.select_card(state_id)
        state = self.repository.get_by_id(state_id)
        if not state: return
        
        # Try to find a related .ini file
        ini_path = self._find_related_ini(state)
        if ini_path:
            try:
                with open(ini_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                self.editor_panel.load_content(Path(ini_path).name, content)
                self.current_ini_path = ini_path
            except Exception as e:
                self.editor_panel.load_content("ERROR", f"Could not read file: {e}")
        else:
            self.editor_panel.load_content("NO INI FOUND", "No configuration file detected for this shortcut.")
            
        self._show_editor()

    def _on_folder_clicked(self, state_id):
        if self._accept_action("folder", state_id):
            self._open_folder(state_id)



    def _show_editor(self):
        if self.editor_visible:
            return
        self.editor_visible = True
        
        pw = self.split_section.width()
        ph = self.split_section.height()
        drawer_width = self.drawer_width
        
        # Position and show the dim overlay
        self.dim_overlay.setGeometry(0, 0, pw, ph)
        self.dim_overlay.show()
        
        self.editor_panel.raise_()
        self.editor_panel.show()
        
        self.editor_animation.stop()
        self.editor_animation.setStartValue(QRect(pw, 0, drawer_width, ph))
        self.editor_animation.setEndValue(QRect(pw - drawer_width, 0, drawer_width, ph))
        self.editor_animation.start()

    def _hide_editor(self):
        if not self.editor_visible:
            return
        self.editor_visible = False
        
        # Hide dim overlay
        self.dim_overlay.hide()
        
        pw = self.split_section.width()
        ph = self.split_section.height()
        drawer_width = self.drawer_width
        
        self.editor_animation.stop()
        self.editor_animation.setStartValue(QRect(pw - drawer_width, 0, drawer_width, ph))
        self.editor_animation.setEndValue(QRect(pw, 0, drawer_width, ph))
        self.editor_animation.start()

    def _on_animation_finished(self):
        if not self.editor_visible:
            self.editor_panel.hide()


    def _find_related_ini(self, state):
        # Priority 1: Check working directory for rk7man.ini specifically
        if state.working_directory and Path(state.working_directory).exists():
            wd = Path(state.working_directory)
            target = wd / "rk7man.ini"
            if target.exists(): return str(target)
            
            # Priority 2: Any other .ini in working dir
            inis = list(wd.glob("*.ini"))
            if inis: return str(inis[0])
            
        # Priority 3: Check target exe directory
        if state.target_exe_path:
            p = Path(state.target_exe_path)
            if p.exists():
                parent = p.parent
                target = parent / "rk7man.ini"
                if target.exists(): return str(target)
                
                inis = list(parent.glob("*.ini"))
                if inis: return str(inis[0])
                
        return None

    def _on_pin_toggled(self, state_id, is_pinned):
        if not self._accept_action("pin", state_id, 0.45):
            return
        self.repository.toggle_favorite(state_id)
        # Re-sort and refresh UI to push pinned items to top
        self._refresh_ui()

    def _on_customization_requested(self, state_id):
        if not self._accept_action("customize", state_id):
            return
        state = self.repository.get_by_id(state_id)
        if not state:
            return
            
        dialog = CustomizationDialog(
            state.custom_name, state.custom_color, state.custom_icon,
            state.custom_background, self
        )
        if self.dark_mode:
            apply_widget_theme(dialog, True)
        if dialog.exec():
            name, color, icon, background = dialog.get_values()
            self.repository.save_customization(state_id, name, color, icon, background)
            self._refresh_ui()


    def _load_settings(self):
        if getattr(sys, 'frozen', False):
            # Running as bundled EXE
            bundle_dir = Path(sys.executable).parent
        else:
            # Running as script
            bundle_dir = Path(__file__).parent.parent

        self.settings_file = bundle_dir / "settings.json"
        if self.settings_file.exists():
            import json
            try:
                with open(self.settings_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_setting(self, key, value):
        import json
        settings = self._load_settings()
        settings[key] = value
        try:
            with open(self.settings_file, "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def _set_status_filter(self, filter_name):
        self.all_filter_btn.setChecked(filter_name == "all")
        self.pinned_filter_btn.setChecked(filter_name == "pinned")
        self.running_filter_btn.setChecked(filter_name == "running")
        self.cluster_list.set_status_filter(filter_name)

    def _refresh_with_feedback(self):
        self._refresh_ui()
        self.header.subtitle_lbl.setText("Library updated just now")
        subtitle = "Launch and monitor environments from one place"
        QTimer.singleShot(1200, lambda: self.header.subtitle_lbl.setText(subtitle))

    def _apply_responsive_columns(self):
        if not hasattr(self, "cluster_list"):
            return
        columns = 3 if self.width() >= 1420 else 2
        self.cluster_list.set_columns(columns)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_editor_geometry()
        self._apply_responsive_columns()

    def _update_editor_geometry(self):
        if not hasattr(self, 'editor_panel') or not hasattr(self, 'split_section'):
            return
        if self.editor_animation.state() == QPropertyAnimation.State.Running:
            return
        
        pw = self.split_section.width()
        ph = self.split_section.height()
        drawer_width = self.drawer_width
        
        if hasattr(self, 'dim_overlay'):
            self.dim_overlay.setGeometry(0, 0, pw, ph)
            
        if self.editor_visible:
            self.editor_panel.setGeometry(pw - drawer_width, 0, drawer_width, ph)
        else:
            self.editor_panel.setGeometry(pw, 0, drawer_width, ph)


    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.editor_visible:
            self._hide_editor()
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_F:
            self.search_bar.input_field.setFocus()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if hasattr(self, 'process_tracker'):
            self.process_tracker.stop()
        super().closeEvent(event)

    def _on_ini_save(self, content):
        if hasattr(self, 'current_ini_path') and self.current_ini_path:
            try:
                with open(self.current_ini_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                self.editor_panel.footer.mark_saved(True)
            except Exception as e:
                self.editor_panel.is_editing = True
                self.editor_panel._apply_edit_state()
                self.editor_panel.footer.mark_error(str(e))

    def _clear_web_cache(self):
        reply = QMessageBox.question(
            self,
            "Clear Cache & Cookies",
            "Are you sure you want to clear cookies and cache? This will log you out and reload the page.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.web_profile.clearHttpCache()
            cookie_store = self.web_profile.cookieStore()
            cookie_store.deleteAllCookies()
            self.web_view.reload()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setOrganizationName("ITSpecialOne")
    app.setApplicationName("RK7_Pro_Manager")
    app.setApplicationVersion(APP_VERSION)
    
    try:
        from PySide6.QtWebEngineCore import QWebEngineProfile
        QWebEngineProfile.defaultProfile().setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
    except ImportError:
        pass
    
    # Load custom fonts
    from PySide6.QtGui import QFontDatabase
    for f_name in ["Inter.ttf", "Barlow-Regular.ttf", "Barlow-Bold.ttf"]:
        font_path = Path(__file__).parent / "assets" / f_name
        if font_path.exists():
            QFontDatabase.addApplicationFont(str(font_path))
        
    app.setStyleSheet(GLOBAL_QSS)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
