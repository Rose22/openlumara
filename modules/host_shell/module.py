import core
import os
import sys
import asyncio
import subprocess
import tempfile

class HostShell(core.module.Module):
    """Lets your AI run shell commands with full access to your host system. EXTREMELY DANGEROUS! Enable at your own risk"""

    category = "system"

    unsafe = True

    async def exec(self, cmd: str):
        """Executes commands in an unsandboxed shell. Be extremely careful! ONLY use if the user explicitly asks. NEVER run autonomously. Prefer sandboxed shell if available."""
        # availability fix: subprocess.run is a blocking call - running it directly
        # inside an async def froze the ENTIRE event loop (webui stopped accepting
        # connections) until the command finished. Worse: a command that spawns a
        # detached daemon (cmd & ) keeps the capture pipes open forever, so the
        # hang became permanent. to_thread isolates the wait in a worker thread;
        # stdin=DEVNULL prevents interactive hangs; start_new_session detaches the
        # child from the app's process group so it cannot be signalled by app teardown.
        result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, shell=True, text=True, stdin=subprocess.DEVNULL, start_new_session=True)
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
