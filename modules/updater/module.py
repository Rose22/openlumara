import core
import os
import subprocess

class Updater(core.module.Module):
    """lets you update openlumara remotely using a `/update` command"""

    @core.module.command("update")
    async def update(self, args: list):
        proc = subprocess.Popen(
            ["sh", "update.sh"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        out, err = proc.communicate()

        output = str(out)
        if err:
            output += f"\nErrors:\n{err}"

        await self.channel.push(output, defer=False)
        await self.manager.restart(hard=True)
