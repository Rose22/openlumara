import core
import os
import sys
import time
import traceback
import urllib.parse

def log(category: str, msg: str):
    """
    simple console log
    WARNING: strictly for cases where the manager or channel instance(s) cannot be accessed
    for example during config loading

    using this will print into the terminal if the manager isn't loaded,
    but otherwise will use the proper logging path via the manager

    so this is a last resort
    """
    if not core.manager.global_instance:
        print(f"[{category.upper()}] {msg}", flush=True)
    else:
        core.manager.global_instance.log(category, msg)

def detail_error(e: Exception):
    """provides more detail about an exception, but in a compact format"""

    # just return the normal message if debug mode is off
    if not core.debug:
        return str(e)

    # lots of detail for debugging!
    return f"{e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}\n\n{traceback.format_exc()}"

def log_error(msg: str, e: Exception):
    """
    console log but with extra spice for errors
    WARNING: strictly for cases where the manager or channel instance(s) cannot be accessed
    for example during config loading
    """
    if not core.manager.global_instance:
        print(f"[ERROR] {msg}: {detail_error(e)}")
        traceback.print_exception(e, file=sys.stdout)
    else:
        tb = traceback.format_exception(e)
        core.manager.global_instance.log("error", f"{msg}: {detail_error(e)}\n{tb}")

def get_path(path: str = ""):
    """get path relative to the project root directory. returns root path if no path is specified."""
    project_root = os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        os.pardir
    ))

    if not path:
        return project_root

    if os.path.isabs(path):
        # return an absolute path as-is
        return path
    else:
        # is a relative path, return it sandboxed to the project root
        return sandbox_path(project_root, path)

def get_data_path(subpath=None):
    """get path to the data directory. contains all persistent data used by the framework"""

    data_path = core.config.get("core", {}).get("data_folder", "data")

    # if it's a relative path, resolve it from the project root
    if not os.path.isabs(data_path):
        data_path = core.get_path(data_path)

    # create it if it doesn't exist
    if not os.path.exists(data_path):
        os.makedirs(data_path, exist_ok=True)

    return sandbox_path(data_path, subpath) if subpath else data_path

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst

def validate_path_string(path: str) -> str:
    """
    validates a path string for traversal and encoding attacks.
    """
    # Strip path separators
    path = path.strip(os.path.sep)

    # Handle URL encoding (check for double/triple encoding)
    decoded = path
    for _ in range(3):
        decoded = urllib.parse.unquote(decoded)

    # normalize slashes after decoding to prevent windows join bypasses
    decoded = decoded.replace("\\", os.sep).replace("/", os.sep)
    # strip again in case unquote introduced new separators
    decoded = decoded.strip(os.path.sep)

    # Check for traversal and null bytes
    if ".." in decoded or "\x00" in decoded:
        raise ValueError("Path traversal is not allowed")

    return decoded

def sandbox_path(base_path: str, requested_path: str) -> str:
    """
    protects against path traversal attacks and the like
    """
    path = requested_path

    # we dont use os.path.normpath here because it resolves '..' and allows path traversal
    # so we do the cross-platform stuff manually instead....
    # using a simple string replacement :(
    normalised_base_path = base_path.replace("\\", os.path.sep)
    normalised_base_path = normalised_base_path.replace("/", os.path.sep)
    
    path = requested_path.replace("\\", os.path.sep)
    path = path.replace("/", os.path.sep)

    # remove path separator at the beginning and end
    path = path.strip(os.path.sep)

    # remove the base path from it in case the AI/user inserts it
    prefix = normalised_base_path + os.sep
    if path.startswith(prefix):
        path = path[len(prefix):]
    elif path == normalised_base_path:
        path = ""

    decoded = validate_path_string(path)

    # block symlink paths
    if hasattr(os, 'O_NOFOLLOW'):
        # check if any component is a symlink
        parts = decoded.split(os.path.sep)
        for i, part in enumerate(parts):
            if i == 0:
                continue  # Skip root
            test_path = os.path.join(normalised_base_path, *parts[:i])
            if os.path.islink(test_path):
                raise ValueError("Symlinks are not allowed in the path")

    if not path:
        return normalised_base_path

    # more path traversal protection
    path_in_base = os.path.join(normalised_base_path, os.path.normpath(decoded))
    
    try:
        real_path = os.path.realpath(path_in_base)
    except (OSError, ValueError):
        raise ValueError(f"Invalid path: {requested_path}")

    if os.path.islink(path_in_base):
        raise ValueError("Symlinks are not allowed in the requested path")

    base_prefix = normalised_base_path + os.sep

    if sys.platform == "win32":
        check_path = real_path.lower()
        check_prefix = base_prefix.lower()
        check_base = normalised_base_path.lower()
    else:
        check_path = real_path
        check_prefix = base_prefix
        check_base = normalised_base_path

    if check_path.startswith(check_prefix) or check_path == check_base:
        return real_path
    else:
        raise ValueError("Access denied: target path is outside sandbox")
1
