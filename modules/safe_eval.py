import core
import subprocess
import shutil

class SafeEval(core.module.Module):
    """runs python code in a docker container"""
    async def run(self, code: str):
        program = None
        if shutil.which("podman"):
            program = "podman"
        elif shutil.which("docker"):
            program = "docker"

        else:
            return self.result({
                "stdout": "",
                "stderr": "error: neither docker nor podman is available"
            })

        try:
            result = subprocess.run(
                [program, 'run', '--rm', 'python:3.11', 'python', '-c', code],
                capture_output=True,
                timeout=30
            )
            return self.result({
                "stdout": result.stdout.decode(),
                "stderr": result.stderr.decode()
            })
        except subprocess.TimeoutExpired:
            return self.result({
                "stdout": "",
                "stderr": "error: execution timed out after 30 seconds"
            })
        except Exception as e:
            return self.result({
                "stdout": "",
                "stderr": f"Error: {str(e)}"
            })
