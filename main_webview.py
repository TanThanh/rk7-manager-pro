import ctypes
import io
import logging
import os
import sys
from pathlib import Path

# Force UTF-8 standard streams with replace handler to avoid Windows ANSI/CP1252 charmap crashes
if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

if sys.stderr is not None:
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

import webview

from web_bridge import WebBridgeAPI


class IssueWebViewPanel:
    """Show the issue site beside the existing HTML sidebar in a separate WebView2 control."""

    URL = "https://ghiissue.itspecialone.site/"

    def __init__(self, window):
        import clr

        clr.AddReference("System.Windows.Forms")
        from System import Action, Uri
        from System.Windows.Forms import DockStyle, Panel
        from webview.platforms.edgechromium import WebView2, CoreWebView2CreationProperties

        self._form = window.native
        self._action_type = Action
        self._uri_type = Uri
        self._state = "idle"
        self._error = None

        def create():
            host = Panel()
            host.Visible = False
            browser = WebView2()
            properties = CoreWebView2CreationProperties()
            # Use a separate persistent profile so the two WebView2 controls
            # cannot conflict over different environment creation options.
            issue_profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RK7ProManager" / "IssueWebView2"
            issue_profile.mkdir(parents=True, exist_ok=True)
            properties.UserDataFolder = str(issue_profile)
            browser.CreationProperties = properties
            browser.CoreWebView2InitializationCompleted += self._on_initialized
            browser.NavigationCompleted += self._on_navigation_completed
            browser.Dock = DockStyle.Fill
            host.Controls.Add(browser)
            self._form.Controls.Add(host)
            host.BringToFront()
            self._host = host
            self._browser = browser
            self._loaded = False
            self._update_bounds()
            self._form.Resize += lambda _sender, _args: self._update_bounds()

        if self._form.InvokeRequired:
            self._form.Invoke(Action(create))
        else:
            create()

    def _update_bounds(self):
        sidebar_width = int(240 * self._form._scale)
        size = self._form.ClientSize
        self._host.SetBounds(sidebar_width, 0, max(0, size.Width - sidebar_width), size.Height)

    def _on_initialized(self, _sender, args):
        if not args.IsSuccess:
            self._state = "error"
            self._error = f"WebView2 could not start: {args.InitializationException}"
            self._host.Visible = False

    def _on_navigation_completed(self, _sender, args):
        if args.IsSuccess:
            self._state = "ready"
            self._error = None
        else:
            self._state = "error"
            self._error = f"Could not load Ghi Issue ({args.WebErrorStatus}). Check the site connection and retry."
            self._host.Visible = False

    def get_status(self):
        return {"state": self._state, "error": self._error}

    def set_visible(self, visible):
        def apply():
            if visible and not self._loaded:
                self._state = "loading"
                self._error = None
                self._browser.EnsureCoreWebView2Async(None)
                self._browser.Source = self._uri_type(self.URL)
                self._loaded = True
            elif visible and self._state == "error":
                self._state = "loading"
                self._error = None
                if self._browser.CoreWebView2 is None:
                    self._browser.EnsureCoreWebView2Async(None)
                    self._browser.Source = self._uri_type(self.URL)
                else:
                    self._browser.Reload()
            self._update_bounds()
            self._host.Visible = visible
            if visible:
                self._host.BringToFront()

        if self._form.InvokeRequired:
            self._form.Invoke(self._action_type(apply))
        else:
            apply()


try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    resource_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).parent)).resolve()
    data_dir = Path(sys.executable).parent.resolve() if getattr(sys, "frozen", False) else Path(__file__).parent.resolve()
    html_path = resource_dir / "web_ui" / "index.html"
    api = WebBridgeAPI(data_dir=data_dir)

    window = webview.create_window(
        title="RK7 PRO - Shortcut Manager",
        url=f"file:///{str(html_path).replace(os.sep, '/')}",
        js_api=api,
        width=1440,
        height=860,
        min_size=(1024, 680),
        maximized=True,
        background_color="#F3F4F6",
        text_select=False,
    )
    api.set_window(window)
    services_started = False

    def on_loaded():
        nonlocal services_started
        if not services_started:
            services_started = True
            try:
                api.set_issue_panel(IssueWebViewPanel(window))
            except Exception as exc:
                api.set_issue_error(f"Could not initialize Ghi Issue: {exc}")
            api.start_background_services()

    window.events.loaded += on_loaded
    main_profile = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "RK7ProManager" / "WebViewData"
    main_profile.mkdir(parents=True, exist_ok=True)
    webview.start(debug=False, private_mode=False, storage_path=str(main_profile))


if __name__ == "__main__":
    main()
