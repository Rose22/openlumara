import asyncio
import core
import shutil
import os
import uuid
import time

class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands in a disposable sandboxed container.
    Container is created, command runs, then container is immediately killed.
    Runs asynchronously to prevent blocking the framework.
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
        "output_limit": {
            "default": 2000,
            "description": "Maximum amount of characters before output gets truncated. Prevents resource exhaustion attacks that overflow the application using too much output"
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
        "read_only": {
            "default": True,
            "description": "Whether the container filesystem is read-only. If enabled, /tmp is mounted as tmpfs for temporary writes."
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

        # Check for gVisor (runsc) availability
        if shutil.which("runsc"):
            self.use_gvisor = True
            core.log("sandbox_shell", "gVisor (runsc) detected. Sandbox will use gVisor for enhanced security.")
        else:
            self.use_gvisor = False
            core.log("sandbox_shell", "Warning: gVisor (runsc) not found. Sandbox is running with standard isolation. To install gVisor for better security, see: https://gvisor.dev/docs/user_guide/install/")

    def _get_unique_name(self):
        """Generate a unique container name to avoid collisions"""
        return f"ol_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"

    async def _run_async_cmd(self, cmd_args, timeout=None):
        """Helper method to run a command asynchronously"""
        process = await asyncio.create_subprocess_exec(
            *cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            return stdout, stderr, process.returncode
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return None, None, -1

    async def run(self, command: str):
        """Runs a command in a sandboxed container asynchronously."""
        if not self.runtime:
            return self.result("Docker or podman not available.", False)

        uid = self.config.get("run_as_user", default="65534")
        timeout = self.config.get("execution_timeout", default=10)
        img = self.config.get("image", default="python:3.11-slim")

        # Generate unique container name
        self.container_name = self._get_unique_name()

        # Build container run command with strict security settings
        # We run in the foreground to capture stdout/stderr directly and reliably
        cmd = [self.runtime, 'run', '--name', self.container_name]

        # Use gvisor runtime if available
        if self.use_gvisor:
            cmd.extend(['--runtime', 'runsc'])
            if self.runtime == "podman":
                cmd.extend(["--runtime-flag", "ignore-cgroups"])

        cmd.extend([
            '--user', uid,
            '--cpus', str(self.config.get("cpu_limit", default=0.5)),
            '--memory', self.config.get("memory_limit", default="256m"),
            '--pids-limit', str(self.config.get("max_processes", default=10)),
            '--network', 'bridge' if self.config.get("internet_access", default=False) else 'none',
            '--stop-timeout', '1'
        ])

        if self.config.get("read_only", default=True):
            cmd.extend(['--read-only', '--tmpfs', '/tmp'])

        if self.config.get("persistent_data", default=True):
            cmd.extend(['-v', f"{self.host_workspace}:/data:Z"])
        else:
            limit = self.config.get("temporary_filesystem_size_limit", default="512m")
            cmd.extend(['--tmpfs', f"/data:size={limit}"])

        cmd.extend(['-w', '/data', img, 'sh', '-c', command])

        output_limit = self.config.get("output_limit")

        try:
            # Run the command in the foreground and capture output directly
            stdout, stderr, exit_code = await self._run_async_cmd(cmd, timeout=timeout)
            
            if stdout is None: # This happens on TimeoutError in _run_async_cmd
                return self.result(f"Command timed out after {timeout}s", False)

            stdout_text = stdout.decode().strip()[:output_limit] if stdout else ""
            stderr_text = stderr.decode().strip()[:output_limit] if stderr else ""

            return self.result({
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code
            })

        except Exception as e:
            return self.result(f"Error running command: {e}", False)
        finally:
            # Always clean up the container
            try:
                await asyncio.wait_for(
                    self._run_async_cmd([self.runtime, 'rm', '-f', self.container_name], timeout=5),
                    timeout=5
                )
            except Exception:
                pass  # Container cleanup failed, but don't fail the whole operation

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
            exit_code = content.get("exit_code", 0)

            output = stdout
            if stderr:
                output += "\n" + stderr

            if exit_code != 0:
                return output if output else f"Command failed with exit code {exit_code}"
            
            return output if output else "NO OUTPUT"
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
