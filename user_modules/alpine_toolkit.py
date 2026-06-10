import core
import subprocess

class AlpineToolkit(core.module.Module):
    """
    Toolkit for verifying and restarting Docker/Podman services on Alpine OpenRC.
    """

    async def on_ready(self):
        core.log("alpine_toolkit", "Alpine Toolkit Module loaded.")

    def check_daemon(self, daemon: str = "podman"):
        """
        Checks the status of the docker/podman daemon socket.
        """
        try:
            cmd = ["rc-service", daemon, "status"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return self.result(f"Status of {daemon}:\n{result.stdout}\n{result.stderr}")
        except Exception as e:
             return self.result(f"Failed to check {daemon} status: {e}", success=False)

    def restart_daemon(self, daemon: str = "podman"):
        """
        Restarts the docker/podman service via OpenRC.
        Requires sudo or root access in some cases.
        """
        try:
            cmd = ["sudo", "rc-service", daemon, "restart"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            return self.result(f"Restarted {daemon}:\n{result.stdout}\n{result.stderr}")
        except Exception as e:
             return self.result(f"Failed to restart {daemon}: {e}", success=False)
