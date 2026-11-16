
import time
import subprocess
import psutil
from pathlib import Path
from unittest.mock import MagicMock
import sys
import os

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from rk7_pro.core.process_tracker import ProcessTrackingService
from rk7_pro.core.models import ShortcutState

def test_responsiveness():
    print("Starting responsiveness test...")
    
    # Mock Repository
    repo = MagicMock()
    state_id = "test_app.lnk"
    test_state = ShortcutState(
        id=state_id,
        name="Test App",
        target_exe_path="C:\\Windows\\System32\\cmd.exe",
        is_running=False
    )
    
    states = {state_id: test_state}
    repo.states = states
    
    def update_state(sid, **kwargs):
        s = states[sid]
        for k, v in kwargs.items():
            setattr(s, k, v)
        print(f"  [Repo] State updated: {sid} -> is_running={s.is_running}, pid={s.process_id}, mode={s.tracking_mode}")
        
    repo.update_state = update_state
    
    tracker = ProcessTrackingService(repo)
    
    # 1. Start a process
    print("1. Launching dummy process (cmd.exe)...")
    proc = subprocess.Popen(["cmd.exe", "/c", "timeout /t 10"], creationflags=subprocess.CREATE_NO_WINDOW)
    
    # Manually mark as running (simulating launch service)
    test_state.is_running = True
    test_state.process_id = proc.pid
    test_state.tracking_mode = "pid"
    
    tracker.start()
    time.sleep(1) # Let tracker initialize
    
    print(f"2. Current state: is_running={test_state.is_running}, pid={test_state.process_id}")
    
    # 3. Kill the process and measure time to detect
    print("3. Killing process now...")
    start_time = time.time()
    proc.terminate()
    
    # Wait for tracker to update state
    timeout = 5
    detected = False
    while time.time() - start_time < timeout:
        if not test_state.is_running:
            end_time = time.time()
            elapsed = end_time - start_time
            print(f"✅ Detected process stop in {elapsed:.2f} seconds!")
            detected = True
            break
        time.sleep(0.1)
        
    if not detected:
        print("❌ Timeout: Tracker failed to detect process stop within 5 seconds.")
        
    tracker.stop()
    print("Test finished.")

if __name__ == "__main__":
    test_responsiveness()
