# rk7_pro/core/models.py
from dataclasses import dataclass
from typing import Optional

@dataclass
class ShortcutState:
    id: str  # Original .lnk filename
    name: str # Cleaned display name
    is_pinned: bool = False
    is_running: bool = False
    
    # Process Tracking Metadata
    process_id: Optional[int] = None
    target_exe_path: Optional[str] = None
    working_directory: Optional[str] = None
    arguments: Optional[str] = None
    tracking_mode: str = "stopped"  # pid, metadata, stopped
    
    # Customization Metadata
    custom_name: Optional[str] = None
    custom_color: Optional[str] = None
    custom_icon: Optional[str] = None
    custom_background: Optional[str] = None
