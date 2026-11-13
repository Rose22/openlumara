import core
import os
import subprocess
import sys

class Updater(core.module.Module):
    """lets you update openlumara remotely using a `/update` command"""

    category = "core"

    @core.module.command("update")
    async def update(self, args: list):
        if sys.platform == "win32":
            update_cmd = ["update.bat"]
        else:
            update_cmd = ["sh", "update.sh"]

        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"

        proc = subprocess.Popen(
            update_cmd,
            cwd=os.getcwd(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        out, err = proc.communicate()

        output = out.decode(errors="replace")
        if err:
            output += f"\nErrors:\n{err.decode(errors='replace')}"

        await self.channel.push(output, defer=False)
        await self.manager.restart(hard=True)

        return output
