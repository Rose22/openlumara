import core
import subprocess
import shutil
import os
from pathlib import Path

class DockerShell(core.module.Module):
    """
    Lets your AI safely run shell commands sandboxed in a Docker container
    """

    settings = {
        # Resource constraints
        "cpu_limit": "0.5",
        "memory_limit": "256m",
        "pids_limit": 50,
        "execution_timeout": 30,

        # Security & Isolation
        "networking": False,         # "none", "host", or "bridge"
        "read_only_rootfs": True,       # Protects the container's system files

        # Persistence (The Workspace)
        "workspace_host_path": "docker_workspace", # Folder on your actual computer
        "workspace_container_path": "/workspace",    # Path inside the container
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure the host workspace directory exists immediately on module load
        host_path = Path(self.config.get("workspace_host_path", "./shell_workspace"))
        host_path.mkdir(parents=True, exist_ok=True)

    async def run(self, command: str):
        """Executes a shell command within the sandbox."""

        # 1. Determine Runtime
        program = "podman" if shutil.which("podman") else "docker"

        if not program or not shutil.which(program):
            return self.result(f"Runtime '{program}' is not installed or available.", False)

        # 2. Build the Base Command
        # We use 'sh -c' to allow the AI to use pipes (|), redirects (>), and logic.
        cmd = [
            program, 'run', '--rm',
            '--cpus', self.config.get("cpu_limit", "0.5"),
            '--memory', self.config.get("memory_limit", "256m"),
            '--pids-limit', str(self.config.get("pids_limit", 50)),
            '--security-opt', 'no-new-privileges',
            '--network', "host" if self.config.get("networking") else "none",
            "python:3.11-slim",
            'sh', '-c', command
        ]

        # 3. Apply Read-Only logic
        # If rootfs is read-only, we MUST mount the workspace so the AI can actually write anything.
        if self.config.get("read_only_rootfs", True):
            cmd.append('--read-only')

        # 4. Apply Persistence (Volume Mounting)
        host_workspace = core.get_path(self.config.get("workspace_host_path", "shell_workspace"))
        container_workspace = self.config.get("workspace_container_path", "/workspace")

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

    @core.module.command("shell", temporary=True)
    async def cmd_shell(self, args):
        """Run a command in the sandboxed shell."""
        if not args:
            return "Usage: shell [command]"
        return await self.run(" ".join(args))

    @core.module.command("shell_setup", temporary=True)
    async def cmd_setup(self, args):
        """Show current shell configuration."""
        conf = (
            f"Runtime: {self.config.get('runtime_preference')}\n"
            f"Image: {self.config.get('base_image')}\n"
            f"Host Workspace: {os.path.abspath(self.config.get('workspace_host_path'))}\n"
            f"Container Workspace: {self.config.get('workspace_container_path')}\n"
            f"Network: {self.config.get('network_mode')}"
        )
        return conf
