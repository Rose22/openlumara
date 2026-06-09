import core
import os
import sys
import time
import traceback
import urllib.parse

def log(category: str, msg: str):
    """simple console log"""
    if not core.quiet:
        print(f"[{category.upper()}] {msg}", flush=True)

def detail_error(e: Exception):
    """provides more detail about an exception, but in a compact format"""

    return f"{e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}\n\n{traceback.format_exc()}"

def log_error(msg: str, e: Exception):
    """console log but with extra spice for errors"""
    if core.debug:
        log("error", f"{msg}: {detail_error(e)}")
        traceback.print_exception(e, file=sys.stdout)
    else:
        log("error", f"{msg}: {e}")

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def get_path(path: str = ""):
    """get path relative to the project root directory. returns root path if no path is specified."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    
    if not path:
        return base_dir

    # Normalize path to catch traversal tricks before processing
    path = os.path.normpath(path)
    
    # Resolve to absolute path first
    if path.startswith(os.path.sep):
        full_path = os.path.abspath(path)
    else:
        full_path = os.path.abspath(os.path.join(base_dir, path))
    
    # Validate that the resolved path stays within the base directory
    validated = validate_path_in_directory(base_dir, full_path)
    if validated is None:
        raise ValueError(f"Path escapes project root: {path}")
    
    return full_path

def get_data_path(subpath: str = ""):
    """get path to a file/folder within the data directory"""
    data_folder = core.config.get("core", {}).get("data_folder", "data")
    data_dir = data_folder
    
    if subpath:
        # Normalize subpath to catch traversal tricks
        subpath = os.path.normpath(subpath)
        
        # Validate the subpath stays within the data directory
        full_subpath = os.path.abspath(os.path.join(data_dir, subpath))
        validated = validate_path_in_directory(data_dir, full_subpath)
        if validated is None:
            raise ValueError(f"Path escapes data directory: {subpath}")
        data_dir = full_subpath

    # create it if it doesn't exist
    if not os.path.exists(data_dir):
        os.makedirs(data_dir, exist_ok=True)

    return data_dir

def validate_path_in_directory(base_dir: str, target_path: str) -> str | None:
    """
    Validates that target_path is safely within base_dir (sandbox).
    Prevents path traversal, symlinks, and null bytes.
    """
    # Normalize the path first to catch tricks like a/./b/../c
    try:
        normalized_path = os.path.normpath(target_path)
    except (OSError, ValueError):
        return None

    try:
        real_path = os.path.realpath(normalized_path)
    except (OSError, ValueError):
        return None

    # Decode URL encoding to catch hidden traversal attempts
    decoded = normalized_path
    for _ in range(3):
        decoded = urllib.parse.unquote(decoded)

    # Check for path traversal and null bytes AFTER decoding
    if ".." in decoded or "\x00" in decoded:
        raise ValueError("Path traversal is not allowed")

    # Check symlinks on the final path
    if os.path.islink(normalized_path):
        return None

    # Scan every component of the path for symlinks (prevents symlink escape via parent dirs)
    parts = normalized_path.split(os.path.sep)
    for i in range(1, len(parts)):
        test_path = os.path.join(*parts[:i])
        if os.path.islink(test_path):
            return None

    # Normalize base dir for comparison
    real_base = os.path.realpath(base_dir)
    
    # Handle case-insensitivity on Windows
    if sys.platform == "win32":
        check_path = real_path.lower()
        check_base = real_base.lower()
    else:
        check_path = real_path
        check_base = real_base

    # Check if path is inside the base directory
    if check_path.startswith(check_base + os.path.sep) or check_path == check_base:
        return os.path.relpath(real_path, real_base)

    return None
