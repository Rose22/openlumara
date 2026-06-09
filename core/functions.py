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

def get_path(path: str = ""):
    """get path relative to the project root directory. returns root path if no path is specified."""
    if not path:
        return os.path.join(
            os.path.dirname(__file__),
            os.pardir
        )

    if path.startswith(os.path.sep):
        # is an absolute path
        return path
    else:
        # is a relative path
        return os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            os.pardir,
            path
        ))

def get_data_path():
    """get path to the data directory. contains all persistent data used by the framework"""

    data_path = core.get_path(
        core.config.get("core", {}).get("data_folder", "data")
    )

    # create it if it doesn't exist
    if not os.path.exists(data_path):
        os.makedirs(data_path, exist_ok=True)

    return data_path

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def secure_path(base_path: str, requested_path: str) -> str:
    """
    protects against path traversal attacks and the like
    """
    path = requested_path

    # remove path separator at the beginning and end
    path = path.strip(os.path.sep)

    # remove the base path from it in case the AI/user inserts it
    prefix = base_path + os.sep
    if path.startswith(prefix):
        path = path[len(prefix):]
    elif path == base_path:
        path = ""

    # basic path traversal prevention
    decoded = path
    for _ in range(3):  # Handle double/triple encoding
        decoded = urllib.parse.unquote(decoded)

    if ".." in decoded or "\x00" in decoded:
        raise ValueError("Path traversal is not allowed")

    # block symlink paths
    if hasattr(os, 'O_NOFOLLOW'):
        # check if any component is a symlink
        parts = decoded.split(os.path.sep)
        for i, part in enumerate(parts):
            if i == 0:
                continue  # Skip root
            test_path = os.path.join(base_path, *parts[:i])
            if os.path.islink(test_path):
                raise ValueError("Symlinks are not allowed in the path")

    if not path:
        return base_path

    # more path traversal protection
    path_in_base = os.path.join(base_path, os.path.normpath(decoded))
    
    try:
        real_path = os.path.realpath(path_in_base)
    except (OSError, ValueError):
        raise ValueError(f"Invalid path: {requested_path}")

    if os.path.islink(path_in_base):
        raise ValueError("Symlinks are not allowed in the requested path")

    base_prefix = base_path + os.sep

    if sys.platform == "win32":
        check_path = real_path.lower()
        check_prefix = base_prefix.lower()
    else:
        check_path = real_path
        check_prefix = base_prefix

    if check_path.startswith(check_prefix) or check_path == base_path:
        return real_path
    else:
        raise ValueError("Access denied: target path is outside sandbox")

