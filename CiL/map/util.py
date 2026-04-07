"""Utility functions"""

from pathlib import Path


def user_cache_dir():
    r"""Return path to application cache directory

    For different platforms, cache directories are:
        Windows:    C:\Users\<username>\AppData\Local\dearpygui_map\Cache
        Mac OS X:   ~/Library/Caches/dearpygui_map
        Unix:       ~/.cache/dearpygui_map
    """
    app_name = "dearpygui_map"
    local_temp = Path.home() / "AppData" / "Local" / app_name / "Cache"
    if _path_is_ascii(local_temp):
        return Path.home() / "AppData" / "Local" / app_name / "Cache"
    return Path(__file__).parent / ".cache" / app_name

def _path_is_ascii(path: Path) -> bool:
    """Checks whether the path contains special characters (DPG has issues with them)."""
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False