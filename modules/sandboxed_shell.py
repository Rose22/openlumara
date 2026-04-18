import core
import subprocess
import shutil
import os
import json
from pathlib import Path

class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands sandboxed in a Docker container
    """

    settings = {
        # Security & Isolation
        "internet_access": False,         # "none", "host", or "bridge"
        "read-only_system_files": True,       # Protects the container's system files

        # Resource constraints
        "cpu_limit": "0.5",
        "memory_limit": "256m",
        "max_processes": 50,
        "execution_timeout": 30,

        # Persistence (The Workspace)
        "sandbox_path": "docker_workspace", # Folder on your actual computer
        "sandbox_path_inside_container": "/workspace",    # Path inside the container

        "image": "python:3.11-slim",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure the host workspace directory exists immediately on module load
        host_path = Path(self.config.get("sandbox_path", "./shell_workspace"))
        host_path.mkdir(parents=True, exist_ok=True)

        self.runtime = None

        if shutil.which("podman"):
            self.runtime = "podman"
        elif shutil.which("docker"):
            self.runtime = "docker"

    async def run(self, command: str):
        """Executes a shell command within the docker/podman sandbox."""
        if not self.runtime:
            return self.result(f"Docker or podman are not installed or available.", False)

        # 2. Build the Base Command
        # We use 'sh -c' to allow the AI to use pipes (|), redirects (>), and logic.
        cmd = [
            self.runtime, 'run', '--rm',
            '--cpus', self.config.get("cpu_limit", "0.5"),
            '--memory', self.config.get("memory_limit", "256m"),
            '--pids-limit', str(self.config.get("max_processes", 50)),
            '--user', "1000:1000",
            '--security-opt', 'no-new-privileges',
            '--network', "host" if self.config.get("internet_access") else "none",
            self.config.get("image", "python:3.11-slim"),
            'sh', '-c', command
        ]

        # 3. Apply Read-Only logic
        # If rootfs is read-only, we MUST mount the workspace so the AI can actually write anything.
        if self.config.get("read-only_system_files", True):
            cmd.append('--read-only')

        # 4. Apply Persistence (Volume Mounting)
        host_workspace = core.get_path(self.config.get("sandbox_path", "shell_workspace"))
        container_workspace = self.config.get("sandbox_path_inside_container", "/workspace")

        # Mount the host folder to the container folder
        cmd.extend(['-v', f"{host_workspace}:{container_workspace}"])
        # Set the working directory to the workspace so 'ls' or 'cd' works intuitively
        cmd.extend(['-w', container_workspace])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.config.get("execution_timeout", 30)
            )

            return self.result({
                "stdout": result.stdout.decode().strip(),
                "stderr": result.stderr.decode().strip(),
                "exit_code": result.returncode,
                "workspace_used": container_workspace
            })

        except subprocess.TimeoutExpired:
            return self.result("Command timed out.", False)
        except Exception as e:
            return self.result(f"Module Error: {str(e)}", False)

    # ---------------------------------------------------------
    # User Commands
    # ---------------------------------------------------------

    @core.module.command("shell", temporary=False)
    async def cmd_shell(self, args):
        """Run a command in the sandboxed shell."""
        if not args:
            return "Usage: shell [command]"

        try:
            result = await self.run(" ".join(args))
            return result.get("content").get("stdout", "NO OUTPUT")
        except Exception as e:
            return f"error while running sandboxed shell command: {e}"

    @core.module.command("shell_setup", temporary=False)
    async def cmd_setup(self, args):
        """Show current shell configuration."""
        conf = (
            f"Runtime: {self.runtime}\n"
            f"Image: {self.config.get('image')}\n"
            f"Host Workspace: {os.path.abspath(self.config.get('sandbox_path'))}\n"
            f"Container Workspace: {self.config.get('sandbox_path_inside_container')}\n"
            f"Internet enabled: {self.config.get('internet_access')}"
        )
        return conf
