import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path

logger = logging.getLogger("rk7_pro.auto_updater")

CURRENT_VERSION = "4.2.0"
GITHUB_REPO = "TanThanh/rk7-manager-pro"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

class AutoUpdateService:
    def __init__(self, current_version=CURRENT_VERSION, repo=GITHUB_REPO):
        self.current_version = current_version
        self.repo = repo
        self._downloading = False
        self._progress = 0

    def check_update(self):
        """Check GitHub Releases for newer version.
        Returns dict with update status and details.
        """
        try:
            req = urllib.request.Request(
                f"https://api.github.com/repos/{self.repo}/releases/latest",
                headers={"User-Agent": "RK7-Pro-Manager-Updater", "Accept": "application/vnd.github.v3+json"}
            )
            with urllib.request.urlopen(req, timeout=6) as response:
                if response.status != 200:
                    return {"has_update": False, "error": f"HTTP {response.status}"}
                data = json.loads(response.read().decode("utf-8"))

            tag_name = data.get("tag_name", "").strip().lstrip("vV")
            release_notes = data.get("body", "")
            html_url = data.get("html_url", "")
            assets = data.get("assets", [])

            # Find matching exe asset (strict priority for exe over zip to prevent corrupted binary replacement)
            exe_asset = None
            for a in assets:
                name = a.get("name", "").lower()
                if name.endswith(".exe"):
                    exe_asset = a
                    break

            if not exe_asset:
                return {
                    "has_update": False,
                    "current_version": self.current_version,
                    "latest_version": tag_name,
                    "error": "Bản phát hành trên GitHub chưa có file .exe cập nhật."
                }

            has_update = self._is_newer(tag_name, self.current_version)
            return {
                "has_update": has_update,
                "current_version": self.current_version,
                "latest_version": tag_name,
                "release_name": data.get("name") or f"Phiên bản {tag_name}",
                "release_notes": release_notes,
                "download_url": exe_asset.get("browser_download_url"),
                "file_name": exe_asset.get("name"),
                "file_size": exe_asset.get("size", 0),
                "html_url": html_url
            }
        except urllib.error.HTTPError as he:
            if he.code == 404:
                return {"has_update": False, "current_version": self.current_version, "message": "Chưa có bản phát hành nào trên GitHub."}
            return {"has_update": False, "error": f"Lỗi kết nối GitHub (HTTP {he.code})"}
        except Exception as ex:
            logger.debug("Failed to check update: %s", ex)
            return {"has_update": False, "error": str(ex)}

    def start_update(self, download_url, file_name=None, progress_callback=None):
        """Download file and launch self-replacement script."""
        if self._downloading:
            return {"success": False, "error": "Đang có tiến trình tải cập nhật khác đang chạy."}

        self._downloading = True
        self._progress = 0

        def _worker():
            try:
                temp_dir = Path(tempfile.gettempdir()) / "rk7_pro_update"
                temp_dir.mkdir(parents=True, exist_ok=True)
                target_name = file_name or "update_package.bin"
                download_path = temp_dir / target_name

                # Download with progress tracking
                req = urllib.request.Request(
                    download_url,
                    headers={"User-Agent": "RK7-Pro-Manager-Updater"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp, open(download_path, "wb") as out_f:
                    total_size = int(resp.headers.get("content-length", 0))
                    downloaded = 0
                    chunk_size = 64 * 1024
                    while True:
                        chunk = resp.read(chunk_size)
                        if not chunk:
                            break
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            pct = int((downloaded / total_size) * 100)
                            self._progress = pct
                            if progress_callback:
                                try:
                                    progress_callback(pct, downloaded, total_size)
                                except Exception:
                                    pass

                # Launch updater script
                self._apply_update_and_restart(download_path)
            except Exception as e:
                logger.error("Update worker error: %s", e)
                if progress_callback:
                    try:
                        progress_callback(-1, 0, 0, str(e))
                    except Exception:
                        pass
            finally:
                self._downloading = False

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return {"success": True, "message": "Bắt đầu tải bản cập nhật..."}

    def _apply_update_and_restart(self, downloaded_file: Path):
        """Generates a batch script that waits for current process to exit,
        replaces the running executable, and restarts it."""
        is_frozen = getattr(sys, "frozen", False)
        current_exe = Path(sys.executable if is_frozen else sys.argv[0]).resolve()

        updater_bat = downloaded_file.parent / "run_updater.bat"
        pid = os.getpid()

        # Batch script instructions
        bat_content = f"""@echo off
chcp 65001 >nul
echo Dang cho ung dung dong hoan toan...
ping 127.0.0.1 -n 3 >nul

:wait_loop
tasklist /fi "PID eq {pid}" 2>nul | find "{pid}" >nul
if not errorlevel 1 (
    ping 127.0.0.1 -n 2 >nul
    goto wait_loop
)

:: Cho he dieu hanh va antivirus nha khoa toan bo file DLL
ping 127.0.0.1 -n 2 >nul

:: Don sach cache _MEI cu de tranh loi load python DLL
for /d %%d in ("%TEMP%\\_MEI*") do (
    rd /s /q "%%d" 2>nul
)

echo Dang cap nhat phien ban moi...
copy /y "{downloaded_file}" "{current_exe}" >nul
if errorlevel 1 (
    echo Loi ghi de file! Dang thu lai...
    ping 127.0.0.1 -n 3 >nul
    copy /y "{downloaded_file}" "{current_exe}" >nul
    if errorlevel 1 (
        echo Cap nhat that bai. Giu lai file da tai: {downloaded_file}
        exit /b 1
    )
)

:: Cho on dinh sau khi ghi de
ping 127.0.0.1 -n 2 >nul

echo Khoi dong lai RK7 Pro Manager...
start "" "{current_exe}"

del "{downloaded_file}" 2>nul
(goto) 2>nul & del "%~f0"
"""
        with open(updater_bat, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # Launch the updater batch detached, then exit application
        flags = 0
        if hasattr(subprocess, "CREATE_NEW_CONSOLE"):
            flags = subprocess.CREATE_NEW_CONSOLE
        elif hasattr(subprocess, "DETACHED_PROCESS"):
            flags = subprocess.DETACHED_PROCESS

        subprocess.Popen(
            ["cmd.exe", "/c", str(updater_bat)],
            creationflags=flags,
            close_fds=True
        )
        os._exit(0)

    @staticmethod
    def _is_newer(latest_tag, current_tag):
        """Compare version strings like 4.0.1 vs 4.0.0."""
        def parse_v(v_str):
            nums = re.findall(r"\d+", str(v_str))
            return tuple(int(x) for x in nums) if nums else (0,)

        return parse_v(latest_tag) > parse_v(current_tag)
