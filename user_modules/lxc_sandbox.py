import core
import subprocess
import shutil
import os

class LxcSandbox(core.module.Module):
    """
    Lets your AI safely run shell commands in an LXC sandbox.
    """

    settings = {
        "container_name": {
            "default": "openlumara-sandbox",
            "description": "Name of the LXC container to use"
        },
        "sandbox_path": {
            "default": "/root/sandbox",
            "description": "The path to the folder your shell will be limited to within the LXC container."
        },
        "execution_timeout": {
            "default": 30,
            "description": "Maximum amount of time a process inside the shell is allowed to run for"
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.runtime = None
        if shutil.which("lxc"):
            self.runtime = "lxc"

        if not self.runtime:
            core.log("lxc_sandbox", "LXC is not available, sandbox shell not started. Please set up LXC to use the LXC sandboxed shell!")
            return False

        self.container_name = self.config.get("container_name", default="openlumara-sandbox")
        self.sandbox_path = self.config.get("sandbox_path", default="/root/sandbox")

        # Check if the container exists
        check_cmd = [self.runtime, 'info', self.container_name]
        try:
            check_res = subprocess.run(check_cmd, capture_output=True, text=True)
            if check_res.returncode != 0:
                 core.log("lxc_sandbox", f"Container '{self.container_name}' does not exist or is not running. Please create and start it.")
                 return False
        except Exception as e:
            core.log("lxc_sandbox", f"Error checking LXC container: {e}")
            return False

        core.log("lxc_sandbox", f"LXC Sandbox initialized using container '{self.container_name}'")

    async def run(self, command: str):
        """Runs a command in the sandboxed LXC environment."""
        if not self.runtime:
            return self.result(f"LXC is not installed or available.", False)

        # Execute the command via 'exec'
        # we prefix it to cd into the sandbox path
        exec_cmd = [
            self.runtime, 'exec',
            self.container_name, '--',
            'sh', '-c', f"mkdir -p {self.sandbox_path} && cd {self.sandbox_path} && {command}"
        ]

        try:
            result = subprocess.run(
                exec_cmd,
                capture_output=True,
                timeout=self.config.get("execution_timeout", default=30)
            )

            return self.result({
                "stdout": result.stdout.decode().strip(),
                "stderr": result.stderr.decode().strip(),
                "exit_code": result.returncode,
                "data_dir": self.sandbox_path
            })

        except subprocess.TimeoutExpired:
            return self.result("Command timed out.", False)
        except Exception as e:
            return self.result(f"Module Error: {str(e)}", False)

    @core.module.command("lxc_shell", send_to_ai=True, help={
        "<cmd>": "runs a command in the LXC sandboxed shell"
    })
    async def cmd_shell(self, args):
        if not args:
            return "Usage: lxc_shell [command]"

        try:
            result = await self.run(" ".join(args))

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
        except Exception as e:
            return f"error while running sandboxed shell command: {e}"

    @core.module.command("lxc_setup", send_to_ai=True)
    async def cmd_setup(self, args):
        """shows details about your sandbox setup"""

        conf = (
            f"Runtime: {self.runtime}\n"
            f"Container Name: {self.container_name}\n"
            f"Sandbox Path: {self.sandbox_path}"
        )
        return conf
