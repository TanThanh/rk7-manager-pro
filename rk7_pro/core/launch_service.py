# rk7_pro/core/launch_service.py
import subprocess
import os
import shlex
from pathlib import Path
from PySide6.QtCore import QObject, Signal as pyqtSignal

class ShortcutLaunchService(QObject):
    launch_started = pyqtSignal(str, int)  # filename, pid
    launch_failed = pyqtSignal(str, str)   # filename, error

    def __init__(self, repository):
        super().__init__()
        self.repo = repository

    def launch(self, filename):
        state = self.repo.states.get(filename)
        if not state:
            return False
            
        try:
            exe_path = state.target_exe_path
            args = state.arguments
            cwd = state.working_directory
            
            # Use strict process launch if metadata is valid and is an executable file
            if exe_path and Path(exe_path).exists() and Path(exe_path).is_file():
                cmd = f'"{exe_path}" {args}' if args else f'"{exe_path}"'
                
                # Use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS so it completely detaches
                creationflags = 0x00000008 | 0x00000200
                
                process = subprocess.Popen(
                    cmd, 
                    cwd=cwd if cwd and Path(cwd).exists() else None,
                    shell=False,
                    creationflags=creationflags,
                    close_fds=True
                )
                
                self.repo.update_state(
                    filename, 
                    is_running=True, 
                    process_id=process.pid,
                    tracking_mode="pid"
                )
                return True
            else:
                # Fallback to direct shell link launch (lose exact PID tracking)
                link_path = self.repo.shortcut_dir / filename
                os.startfile(str(link_path))
                self.repo.update_state(
                    filename, 
                    is_running=True, 
                    process_id=None,
                    tracking_mode="session_fallback"
                )
                return True
                
        except Exception as e:
            print(f"Launch failed for {filename}: {e}")
            return False
