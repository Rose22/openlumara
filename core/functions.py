import core
import os
import sys
import time
import traceback

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
    return get_path("data")

def remove_duplicates(lst: list):
    # removes duplicates from a list

    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst
