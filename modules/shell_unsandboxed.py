import core
import os
import sys
import subprocess
import tempfile

class UnsafeShell(core.module.Module):
    """Lets your AI run shell commands with full access to your system. EXTREMELY DANGEROUS! Enable at your own risk"""

    async def exec(self, cmd: str):
        """Executes commands in an unsandboxed shell. Be extremely careful! ONLY use this if the user explicitely asks for it. NEVER run this autonomously. If a sandboxed shell is available, always prefer using that over the unsafe shell!"""

        result = subprocess.run(cmd, capture_output=True, shell=True, text=True)
        return result
