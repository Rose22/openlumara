import core
import os
import sys
import platform
import datetime

class System(core.module.Module):
    """Inserts information about your system into the system prompt"""

    async def on_system_prompt(self):
        details = {
            "OS": sys.platform,
            "OS release": platform.release(),
            "platform": platform.platform(),
            "architecture": platform.machine() if platform.machine() else "unknown",
            "hostname": platform.node(),
            "home dir": os.path.expanduser("~")
        }

        details_string = ""
        for key, value in details.items():
            details_string += f"{key}: {value}\n"
        details_string = details_string.strip()

        return details_string
