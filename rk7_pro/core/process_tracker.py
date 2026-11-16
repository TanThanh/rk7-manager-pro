# rk7_pro/core/process_tracker.py
import psutil
import time
import os
from pathlib import Path
from PySide6.QtCore import QThread

class ProcessTrackingService(QThread):
    def __init__(self, repository, parent=None):
        super().__init__(parent)
        self.repo = repository
        self.running = True

    def run(self):
        while self.running:
            try:
                # 1. Identify states that are currently marked as running
                active_states = [s for s in self.repo.states.values() if s.is_running]
                
                # States that need a full system process scan because their known PID is gone
                doubtful_states = []
                
                for state in active_states:
                    is_alive = False
                    
                    # PRIORITY 1: Check known PID first (O(1) - Very Fast)
                    if state.process_id and psutil.pid_exists(state.process_id):
                        try:
                            p = psutil.Process(state.process_id)
                            if p.status() != psutil.STATUS_ZOMBIE:
                                is_alive = True
                                
                                # Optional: Child-tracking logic for shell launchers
                                if p.name().lower() in ['cmd.exe', 'conhost.exe']:
                                    children = p.children(recursive=True)
                                    for child in children:
                                        if state.target_exe_path and child.name().lower() == Path(state.target_exe_path).name.lower():
                                            self.repo.update_state(state.id, process_id=child.pid)
                                            break
                        except psutil.NoSuchProcess:
                            pass
                            
                    # Priority 2: Session Fallback (Always stays alive until manual stop)
                    if not is_alive and state.tracking_mode == "session_fallback":
                        is_alive = True
                        
                    # If not discovered by PID and not a session fallback, it might be gone
                    # OR moved to another PID. Queue for deep scan.
                    if not is_alive:
                        if state.target_exe_path:
                            doubtful_states.append(state)
                        else:
                            # No way to track anymore, mark as stopped
                            self.repo.update_state(state.id, is_running=False, process_id=None, tracking_mode="stopped")

                # PRIORITY 3: Deep Scan (O(N) - Scan once for all doubtful states)
                if doubtful_states:
                    self._scan_and_update_states(doubtful_states)
                        
            except Exception as e:
                print(f"Tracking error: {e}")
                
            time.sleep(0.8) # Responsive but light on CPU

    def _scan_and_update_states(self, doubtful_states):
        """Scan all system processes ONCE and update all doubtful states."""
        # Pre-calculate target names to speed up matching (multiple states might use same EXE)
        targets = {}
        for s in doubtful_states:
            name = Path(s.target_exe_path).name.lower()
            if name not in targets:
                targets[name] = []
            targets[name].append(s)
            
        found_ids = set()
        
        # Iterate all processes ONCE, only requesting 'name' initially (highly optimized)
        for p in psutil.process_iter(['name']):
            try:
                p_name = p.info['name']
                if not p_name: continue
                
                p_name_lower = p_name.lower()
                if p_name_lower in targets:
                    # Matched target name, query heavy properties selectively
                    p_info = p.as_dict(attrs=['pid', 'exe', 'cwd', 'cmdline'])
                    p_exe = p_info.get('exe')
                    p_cwd = p_info.get('cwd')
                    p_cmdline = p_info.get('cmdline')
                    p_pid = p_info.get('pid')
                    
                    for state in targets[p_name_lower]:
                        # Skip if already found this state in this scan
                        if state.id in found_ids: continue
                        
                        # Validate match
                        is_match = False
                        # 1. Exact EXE path match match
                        if p_exe and Path(p_exe).resolve() == Path(state.target_exe_path).resolve():
                            if state.working_directory and p_cwd:
                                if Path(state.working_directory).resolve() == Path(p_cwd).resolve():
                                    is_match = True
                            elif state.arguments and p_cmdline:
                                cmd_str = " ".join(p_cmdline)
                                args_list = state.arguments.split()
                                if any(a in cmd_str for a in args_list if a.strip()):
                                    is_match = True
                            elif not state.working_directory and not state.arguments:
                                is_match = True
                                
                        if is_match:
                            self.repo.update_state(state.id, process_id=p_pid, tracking_mode="metadata_match", is_running=True)
                            found_ids.add(state.id)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue

        # Any state that was doubtful and NOT found in the scan is truly stopped
        for state in doubtful_states:
            if state.id not in found_ids:
                self.repo.update_state(state.id, is_running=False, process_id=None, tracking_mode="stopped")

    def stop(self):
        self.running = False
        self.wait()
