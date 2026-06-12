import core
import subprocess
import shutil
import os
import uuid
import time

class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands in a disposable sandboxed container.
    Container is created, command runs, then container is immediately killed.
    """

    settings = {
        "internet_access": {
            "default": False,
            "description": "Whether the sandbox container has access to the internet"
        },
        "persistent_data": {
            "default": True,
            "description": "When on, the /data folder in the sandbox is persistent (and mapped to your host system). When off, it's a temporary folder in RAM (tmpfs)"
        },
        "sandbox_path": {
            "default": "~/sandbox",
            "description": "The path to the folder your shell will be limited to. It can't access anything outside this folder!"
        },
        "execution_timeout": {
            "default": 10,
            "description": "Maximum amount of time (in seconds) a process inside the shell is allowed to run for"
        },
        "cpu_limit": {
            "default": 0.5,
            "type": "percentage",
            "description": "The percentage of CPU use to limit processes inside the sandbox to. They will be prevented from exceeding this limit"
        },
        "memory_limit": {
            "default": "256m",
            "description": "Maximum amount of RAM use to allow (example: 150kb, 256m, 2gb)"
        },
        "max_processes": {
            "default": 10,
            "description": "Maximum amount of processes to allow"
        },
        "temporary_filesystem_size_limit": {
            "default": "512m",
            "description": "Maximum size for the temporary sandbox disk (e.g., 512m, 2g). Only works when persistent_data is off."
        },
        "image": "python:3.11-slim",
        "run_as_user": {
            "default": "65534",
            "description": "User ID to run the container processes as. Defaults to 65534 (nobody) for security."
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runtime = None
        if shutil.which("podman"):
            self.runtime = "podman"
        elif shutil.which("docker"):
            self.runtime = "docker"

        if not self.runtime:
            core.log("sandbox_shell", "Neither docker nor podman are available!")
            return False

        self.host_workspace = os.path.expanduser(self.config.get("sandbox_path", default="~/sandbox"))
        os.makedirs(self.host_workspace, exist_ok=True)

    def _get_unique_name(self):
        """Generate a unique container name to avoid collisions"""
        return f"ol_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"

    async def run(self, command: str):
        """Runs a command in a sandboxed container, then kills it."""
        if not self.runtime:
            return self.result("Docker or podman not available.", False)

        uid = self.config.get("run_as_user", default="65534")
        timeout = self.config.get("execution_timeout", default=10)
        img = self.config.get("image", default="python:3.11-slim")

        # Generate unique container name
        self.container_name = self._get_unique_name()

        # Build container run command
        cmd = [
            self.runtime, 'run', '--rm',
            '--name', self.container_name,
            '--user', uid,
            '--cpus', str(self.config.get("cpu_limit", default=0.5)),
            '--memory', self.config.get("memory_limit", default="256m"),
            '--pids-limit', str(self.config.get("max_processes", default=10)),
            '--network', 'bridge' if self.config.get("internet_access", default=False) else 'none',
            '--stop-timeout', '1'
        ]

        # Handle persistent vs temporary data
        if self.config.get("persistent_data", default=True):
            cmd.extend(['-v', f"{self.host_workspace}:/data:Z"])
        else:
            limit = self.config.get("temporary_filesystem_size_limit", default="512m")
            cmd.extend(['--tmpfs', f"/data:size={limit},mode=1777"])

        # Set working directory and add command
        cmd.extend(['-w', '/data'])
        cmd.extend([img, 'sh', '-c', command])


        try:
            # Run the container with manual timeout handling
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            stdout, stderr = process.communicate(timeout=timeout)
            result = self.result({
                "stdout": stdout.decode().strip(),
                "stderr": stderr.decode().strip(),
                "exit_code": process.returncode,
                "data_dir": "/data"
            })
        except subprocess.TimeoutExpired:
            # Timeout occurred
            process.kill()  # Kill the docker run process
            result = self.result(f"Command timed out after {timeout}s", False)
        finally:
            try:
                # Only kill if the process is still running
                if process.returncode is None:
                    process.kill()
            except Exception:
                pass  # Process is already dead or killed

            try:
                # Explicitly kill the container
                subprocess.run([self.runtime, 'kill', self.container_name], capture_output=True, timeout=5)
            except Exception:
                pass

            # Clean up the container
            try:
                subprocess.run([self.runtime, 'rm', '-f', self.container_name], capture_output=True, timeout=5)
            except Exception:
                pass

            return result

    @core.module.command("shell", send_to_ai=True, help={
        "<cmd>": "runs a command in the sandboxed shell"
    })
    async def cmd_shell(self, args):
        if not args:
            return "Usage: shell [command]"

        try:
            result = await self.run(" ".join(args))
            content = result.get("content")

            if not isinstance(content, dict):
                return content

            stdout = content.get("stdout", "")
            stderr = content.get("stderr", "")

            output = stdout
            if stderr:
                output += "\n" + stderr

            return output if output else "BLANK"
        except Exception as e:
            return f"error while running sandboxed shell command: {e}"

    @core.module.command("shell_setup", send_to_ai=True)
    async def cmd_setup(self, args):
        """shows details about your sandbox setup"""
        return (
            f"Runtime: {self.runtime}\n"
            f"Container Name: {self.container_name}\n"
            f"Image: {self.config.get('image')}\n"
            f"Persistent Data: {self.config.get('persistent_data')}\n"
            f"Internet enabled: {self.config.get('internet_access')}"
        )
