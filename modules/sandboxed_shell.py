import core
import subprocess
import shutil
import os

class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands in a docker/podman sandbox.
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
        "execution_timeout": {
            "default": 30,
            "description": "Maximum amount of time a process inside the shell is allowed to run for"
        },
        "image": "python:3.11-slim",
        "run_as_user": {
            "default": "65534",
            "description": "UID to run the container processes as. Defaults to 65534 (nobody) for security."
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Resolve the host path and ensure it exists.
        self.host_workspace = os.path.expanduser(self.config.get("sandbox_path", default="~/sandbox"))
        if not os.path.exists(self.host_workspace):
            os.makedirs(self.host_workspace, exist_ok=True)

        self.runtime = None
        if shutil.which("podman"):
            self.runtime = "podman"
        elif shutil.which("docker"):
            self.runtime = "docker"

        if not self.runtime:
            core.log("sandbox_shell", "Neither docker nor podman are available, sandbox shell not started. Please set up either docker or podman to use the sandboxed shell!")
            return False

        self.container_name = "openlumara_shell"

        # 1. Check if the container is already running
        is_running = False
        check_cmd = [self.runtime, 'inspect', '-f', '{{.State.Running}}', self.container_name]
        try:
            check_res = subprocess.run(check_cmd, capture_output=True, text=True, timeout=10)
            if check_res.returncode == 0 and check_res.stdout.strip() == "true":
                is_running = True
        except subprocess.TimeoutExpired:
            core.log("sandbox_shell", "Timeout checking container state. Socket might be hung.")
            is_running = False
        except Exception:
            is_running = False

        # 2. If not running, start a long-lived background container
        if not is_running:
            # remove a lingering container if it's present
            subprocess.run([self.runtime, 'rm', '-f', self.container_name], capture_output=True)

            core.log("sandbox_shell", "Starting container..")

            start_cmd = [
                self.runtime, 'run', '-d',
                '--name', self.container_name,
                '--user', self.config.get("run_as_user", default="65534"),
                '--cpus', str(self.config.get("cpu_limit", default=0.5)),
                '--memory', self.config.get("memory_limit", default="256m"),
                '--pids-limit', str(self.config.get("max_processes", default=50)),
                '--network', 'bridge' if self.config.get("internet_access", default=False) else 'none',
                '--rm',
            ]

            if self.config.get("persistent_data", default=True):
                start_cmd.extend(['-v', f"{self.host_workspace}:/data:Z"])
            else:
                start_cmd.extend(['--tmpfs', '/data'])

            # set working dir to /data
            start_cmd.extend(['-w', '/data'])

            start_cmd.extend([
                self.config.get("image", default="python:3.11-slim"),
                'tail', '-f', '/dev/null'  # Keep it alive
            ])

            try:
                subprocess.run(start_cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError as e:
                return core.log("sandbox_shell", f"Failed to start container: {e.stderr.decode()}")

            core.log("sandbox_shell", "Container started")

    async def run(self, command: str):
        """Runs a command in the sandboxed Docker/Podman environment."""
        if not self.runtime:
            return self.result(f"Docker or podman are not installed or available.", False)

        # Execute the command via 'exec'
        exec_cmd = [
            self.runtime, 'exec',
            self.container_name,
            'sh', '-c', command
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
                "data_dir": "/data"
            })

        except subprocess.TimeoutExpired:
            return self.result("Command timed out.", False)
        except Exception as e:
            return self.result(f"Module Error: {str(e)}", False)

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

    @core.module.command("shell_setup", send_to_ai=True)
    async def cmd_setup(self, args):
        """shows details about your sandbox setup"""

        conf = (
            f"Runtime: {self.runtime}\n"
            f"Container Name: {self.container_name}\n"
            f"Image: {self.config.get('image')}\n"
            f"Persistent Data: {self.config.get('persistent_data')}\n"
            f"Internet enabled: {self.config.get('internet_access')}"
        )
        return conf

    async def on_shutdown(self):
        """
        Triggered when OpenLumara shuts down.
        Stops and removes the persistent container to keep the host clean.
        """
        if not self.runtime:
            return

        stop_cmd = [self.runtime, 'kill', self.container_name]
        rm_cmd = [self.runtime, 'rm', self.container_name]

        core.log("sandbox_shell", "shutting down container")

        try:
            # We attempt to stop and remove, but ignore errors if the container
            # doesn't exist or wasn't running.
            subprocess.run(stop_cmd, capture_output=True)
            subprocess.run(rm_cmd, capture_output=True)
        except Exception:
            pass
