import core
import os
import sys
import subprocess
import shlex
import resource
import tempfile
import shutil


class ShellSandbox(core.module.Module):
    """Enables the AI to run shell commands. Restricted to a temporary directory."""

    def _set_limits(self):
        """
        Helper function to set resource limits.
        Called inside the child process before exec.
        """
        # 1. Limit max processes (prevents fork bombs)
        # Set to 20 processes (adjust based on your needs)
        resource.setrlimit(resource.RLIMIT_NPROC, (20, 20))

        # 2. Limit file descriptors (prevents resource exhaustion)
        resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))

        # 3. Create new session ID (prevents terminal hijacking)
        os.setsid()

    async def on_ready(self):
        self.using_linux = False
        if sys.platform.lower() == "linux":
            import resource
            self.using_linux = True
            core.log("shell exec", "linux detected - extra sandbox security applied")

    async def exec(self, command: str, timeout: int = 30) -> dict:
        """
        Execute a command safely in a temporary sandbox directory.
        Uses shell=False for safety

        You MUST NOT use shell features like:
            - Pipes (`|`) or redirection (`>`)
            - Shell variables/expansions
        using_linux = False
            - Background processes (`&`)
            - Complex command chaining
        Use simple commands without chaining.

        Sandbox security is NOT PERFECT. Files outside the sandbox directory can still be accessed using absolute paths.
        """
        # 1. Create a dedicated sandbox directory
        workdir = tempfile.mkdtemp(prefix="sandbox_")

        try:
            # Run without shell.
            args = shlex.split(command)

            result = subprocess.run(
                args,
                shell=False,
                timeout=timeout,
                capture_output=True,
                text=True,
                cwd=workdir,
                preexec_fn=self._set_limits if self.using_linux else os.setsid,
            )

            await self.manager.channel.announce(result.stdout)

            return {
                'returncode': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'timed_out': False
            }

        except subprocess.TimeoutExpired:
            return {'returncode': -1, 'stdout': '', 'stderr': 'Command timed out', 'timed_out': True}
        except Exception as e:
            return {'returncode': -1, 'stdout': '', 'stderr': str(e), 'timed_out': False}
        finally:
            # Safely remove the directory
            try:
                shutil.rmtree(workdir)
            except OSError:
                pass # Silently fail if cleanup fails
