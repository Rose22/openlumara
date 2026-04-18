import core
import os
import sys
import subprocess
import tempfile

class UnsafeShell(core.module.Module):
    """Lets your AI run shell commands. EXTREMELY DANGEROUS! Enable at your own risk"""

    async def exec(self, cmd: str):
        """executes commands in an unsandboxed shell. careful!"""

        result = subprocess.run(cmd.split(), capture_output=True, shell=True, text=True)
        return result
