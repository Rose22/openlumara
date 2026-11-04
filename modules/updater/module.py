import core
import os
import subprocess

class Updater(core.module.Module):
    """lets you update openlumara remotely using a `/update` command"""

    @core.module.command("update")
    async def update(self, args: list):
        proc = subprocess.Popen(
            ["git", "pull"],
            stdout=None,
            stderr=None,
        )
        proc.wait()

        await self.manager.restart(hard=True)
