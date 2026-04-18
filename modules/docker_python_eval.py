import core
import subprocess
import shutil

class DockerPythonEval(core.module.Module):
    """Runs python code in a docker container"""
    async def run(self, code: str):
        program = "podman" if shutil.which("podman") else "docker"

        if not program:
            return self.result("neither docker nor podman is available", False)

        try:
            result = subprocess.run(
                [
                    program, 'run', '--rm',
                    # Resource limits
                    '--cpus', '0.5',           # Max 50% CPU
                    '--memory', '128m',        # Max 128MB RAM
                    '--pids-limit', '50',      # Max 50 processes
                    '--security-opt', 'no-new-privileges',  # Prevent privilege escalation
                    # Network isolation
                    '--network', 'none',       # No network access
                    # Read-only filesystem
                    '--read-only',
                    # Run as non-root user
                    '--user', '1000:1000',
                    'python:3.11-slim',        # Use slim image (smaller attack surface)
                    'python', '-c', code
                ],
                capture_output=True,
                timeout=30
            )
            return self.result({
                "stdout": result.stdout.decode(),
                "stderr": result.stderr.decode()
            })
        except subprocess.TimeoutExpired:
            return self.result("process timed out", False)
