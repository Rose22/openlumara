import core
import os
import sys
import subprocess
import tempfile

class UnsafeShell(core.module.Module):
    """Lets your AI run shell commands with full access to your system. EXTREMELY DANGEROUS! Enable at your own risk"""

    unsafe = True

    async def exec(self, cmd: str):
        """Executes commands in an unsandboxed shell. Be extremely careful! ONLY use this if the user explicitely asks for it. NEVER run this autonomously. If a sandboxed shell is available, always prefer using that over the unsafe shell!"""

        result = subprocess.run(cmd, capture_output=True, shell=True, text=True)
        return self.result({
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode
        })

    @core.module.command("shell", help={
        "": "unsafe shell module active. EXTREMELY INSECURE AND UNSAFE.",
        "<cmd>": "runs a command in your system's shell"
    })
    async def cmd_exec(self, args):
        try:
            result = await self.exec(" ".join(args))
        except Exception as e:
            return f"error while running shell command: {e}"

        content = result.get("content")
        if not isinstance(content, dict):
            return content

        stdout = content.get("stdout") if content else ""
        stderr = content.get("stderr") if content else ""

        output = ""
        if stdout:
            output += stdout
        if stderr:
            output += "\n" + stderr

        return output if output else "BLANK"
