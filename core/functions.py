import core
import os
import sys
import time
import traceback

# Runtime overrides for data and config paths
_data_path_override = None
_config_path_override = None

def set_data_path(path: str):
    """Override the default data directory path. Can be absolute or relative to CWD."""
    global _data_path_override
    try:
        resolved_path = os.path.abspath(os.path.expanduser(path))
        log("core", f"Resolving data path: '{path}' -> '{resolved_path}'")
        if not os.path.exists(resolved_path):
            log("core", f"Data directory does not exist, creating: {resolved_path}")
            os.makedirs(resolved_path, exist_ok=True)
        else:
            log("core", f"Data directory exists: {resolved_path}")
        _data_path_override = resolved_path
        log("core", f"✓ Data directory set to: {resolved_path}")
    except Exception as e:
        log("error", f"Failed to set data path '{path}': {e}. Using default.")
        _data_path_override = None

def set_config_path(path: str):
    """Override the default config file path. Can be absolute or relative to CWD."""
    global _config_path_override
    try:
        resolved_path = os.path.abspath(os.path.expanduser(path))
        log("core", f"Resolving config path: '{path}' -> '{resolved_path}'")
        _config_path_override = resolved_path
        log("core", f"✓ Config path set to: {resolved_path}")
    except Exception as e:
        log("error", f"Failed to set config path '{path}': {e}. Using default.")
        _config_path_override = None

def log(category: str, msg: str):
    """simple console log"""
    print(f"[{category.upper()}] {msg}")

def log_error(msg: str, e: Exception):
    """console log but with extra spice for errors"""
    log("error", f"{msg}: {e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}")
    #traceback.print_exception(e, limit=2, file=sys.stdout)

async def restart(channel = None):
    if channel:
        await channel.announce("restarting server..")
    log("core", "restarting server..")

    time.sleep(0.1)
    os.execv(sys.argv[0], sys.argv)

def get_path(path: str = ""):
    """get path relative to the project root directory. returns root path if no path is specified."""
    return os.path.abspath(os.path.join(
        os.path.dirname(__file__),
        os.pardir,
        path
    ))

def get_data_path():
    """Get the data directory path, using override if set, otherwise default."""
    if _data_path_override:
        return _data_path_override
    return get_path("data")

def get_config_path():
    """Get the config file path, using override if set, otherwise default."""
    if _config_path_override:
        return _config_path_override
    return None  # Will be handled by config.py to use default

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst
