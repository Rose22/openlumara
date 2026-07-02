import asyncio
import json
import os
import shutil
import signal
import sys
import uuid

import core


class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands in a disposable sandboxed container.
    The container is persistent for the duration of the application session.
    Runs asynchronously to prevent blocking the framework.
    """

    header = "Shell"

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
            "default": "512m",
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
        "image": {
            "default": "python:3.11-slim",
            "description": "Container image to use for the sandbox"
        },
        "run_as_user": {
            "default": "",
            "description": "User ID to run the container processes as. If left empty, the ID of the host user running OpenLumara will be used."
        }
    }

    async def _kill_process_tree(self, process):
        """Kill a process and all its children (Unix only)."""
        if sys.platform == "win32":
            try:
                process.kill()
                await process.wait()
            except ProcessLookupError:
                pass
        else:
            try:
                pgid = os.getpgid(process.pid)
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, OSError):
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                pass

    async def _run_async_cmd(self, cmd_args, timeout=None, limit=None):
        """
        Helper method to run a command asynchronously with memory-safe output reading.

        Returns: (stdout, stderr, returncode, timed_out)
        """
        if sys.platform == "win32":
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
        else:
            process = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                preexec_fn=os.setsid
            )

        stdout_buf = bytearray()
        stderr_buf = bytearray()

        async def read_stream(stream, buffer):
            while True:
                try:
                    chunk = await stream.read(4096)
                    if not chunk:
                        break
                    if limit is None or len(buffer) < limit:
                        remaining = limit - len(buffer) if limit else len(chunk)
                        buffer.extend(chunk[:remaining])
                except Exception:
                    break

        read_out_task = asyncio.create_task(read_stream(process.stdout, stdout_buf))
        read_err_task = asyncio.create_task(read_stream(process.stderr, stderr_buf))

        timed_out = False
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            timed_out = True
            await self._kill_process_tree(process)
        finally:
            read_out_task.cancel()
            read_err_task.cancel()
            try:
                await asyncio.gather(read_out_task, read_err_task, return_exceptions=True)
            except Exception:
                pass

        return_code = process.returncode if process.returncode is not None else -1
        return bytes(stdout_buf), bytes(stderr_buf), return_code, timed_out

    async def on_system_prompt(self):
        return "".join(self._get_setup())

    async def on_background(self):
        """Monitors container memory usage and kills/restarts if limit is exceeded."""
        # Parse the configured memory limit once to avoid repeated string parsing
        limit_str = self.config.get("memory_limit", default="256m")
        limit_bytes = self._parse_memory_string(limit_str)
        if not limit_bytes:
            limit_bytes = 268435456  # Fallback to 256MB in bytes

        while True:
            try:
                await asyncio.sleep(1)

                if not self.container_name or not self.runtime:
                    continue

                # fetch current memory usage of the container
                try:
                    current_mem_bytes = None

                    # 1. try cgroup v2 and v1 paths
                    for cgroup_path in ['/sys/fs/cgroup/memory.current',
                                        '/sys/fs/cgroup/memory/memory.usage_in_bytes']:
                        try:
                            stdout, _, _, _ = await self._run_async_cmd(
                                [self.runtime, 'exec', self.container_name, 'cat', cgroup_path],
                                timeout=5.0, limit=1024
                            )
                            current_mem_bytes = float(stdout)
                            break
                        except Exception:
                            continue

                    # fallback to runtime stats if cgroup reads failed
                    if current_mem_bytes is None:
                        try:
                            stdout, _, _, _ = await self._run_async_cmd(
                                [self.runtime, 'stats', '--no-stream', '--format', '{{json .}}', self.container_name],
                                timeout=5.0, limit=1024
                            )
                            stats_json = json.loads(stdout.decode('utf-8'))
                            current_mem_bytes = stats_json.get("MemUsage", 0)
                        except Exception:
                            pass

                    # skip loop iteration if we couldn't get a valid memory value
                    if not current_mem_bytes:
                        self.log(self.name, "Warning: Could not get RAM usage. Memory overflow attacks could occur.")
                        continue

                    if current_mem_bytes and current_mem_bytes > limit_bytes:
                        self.log("sandbox_shell", f"Memory limit exceeded ({current_mem_bytes} > {limit_bytes} bytes). Killing container.")
                        await self._kill_container()
                        self.container_name = None

                        self.log("sandbox_shell", "Restarting container due to memory limit...")
                        await self.on_ready()
                except Exception as e:
                    self.log("sandbox_shell", f"Error checking memory stats: {e}")
            except Exception as e:
                self.log("sandbox_shell", f"Background loop error: {e}")
                await asyncio.sleep(5)  # Backoff to prevent tight loop on errors

    async def _kill_container(self):
        """Kills and removes the container."""
        if self.container_name:
            try:
                await self._run_async_cmd([self.runtime, 'kill', self.container_name], timeout=5.0)
            except:
                pass
            try:
                await self._run_async_cmd([self.runtime, 'rm', '-f', self.container_name], timeout=10.0)
            except:
                pass

    def _parse_memory_string(self, mem_str):
        """Converts memory string like '10.23MiB' or '256m' to bytes."""
        if not mem_str:
            return 0
        mem_str = mem_str.strip().upper()
        multipliers = {
            'K': 1024,
            'M': 1024**2,
            'G': 1024**3,
            'T': 1024**4
        }
        
        for suffix, mult in multipliers.items():
            if mem_str.endswith(suffix + 'B') or mem_str.endswith(suffix):
                try:
                    return float(mem_str[:-len(suffix)]) * mult
                except ValueError:
                    return 0
        try:
            return float(mem_str)
        except ValueError:
            return 0

    async def on_ready(self):
        """Starts the persistent container when the module is ready."""
        self.runtime = None
        self.container_name = None
        self.use_gvisor = False

        if shutil.which("podman"):
            self.runtime = "podman"
        elif shutil.which("docker"):
            self.runtime = "docker"

        if not self.runtime:
            self.log("sandbox_shell", "Neither docker nor podman are available!")
            return

        self.host_workspace = os.path.expanduser(self.config.get("sandbox_path", default="~/sandbox"))
        os.makedirs(self.host_workspace, exist_ok=True)

        # Check for gVisor (runsc) availability
        if shutil.which("runsc"):
            self.use_gvisor = True
            self.log("sandbox_shell", "gVisor (runsc) detected. Sandbox will use gVisor for enhanced security.")
        else:
            self.log("sandbox_shell", "Warning: gVisor (runsc) not found. Sandbox is running with standard isolation. To install gVisor for better security, see: https://gvisor.dev/docs/user_guide/install/")

        if not self.runtime:
            return

        uid = self.config.get("run_as_user", default="")
        if not uid:
            try:
                uid = str(os.getuid())
            except AttributeError:
                uid = "1000"

        img = self.config.get("image", default="python:3.11-slim")
        self.container_name = "openlumara_shell"

        cmd = [self.runtime, 'run', '-d', '--rm', '--init', '--name', self.container_name]

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
            selinux_flag = ":Z" if sys.platform != "win32" else ""
            cmd.extend(['-v', f"{self.host_workspace}:/data{selinux_flag}"])
        else:
            limit = self.config.get("temporary_filesystem_size_limit", default="512m")
            cmd.extend(['--tmpfs', f"/data:size={limit}"])

        cmd.extend(['-w', '/data', img, 'tail', '-f', '/dev/null'])

        try:
            stdout, stderr, exit_code, _ = await self._run_async_cmd(cmd, timeout=30.0, limit=1024 * 1024)
            self.log("sandbox_shell", f"Persistent container {self.container_name} started (UID: {uid}).")
        except Exception as e:
            self.log("sandbox_shell", f"Error during container startup: {e}")
            self.container_name = None

    async def on_shutdown(self):
        """Cleans up the container when the application shuts down."""
        if self.container_name and self.runtime:
            self.log("sandbox_shell", f"Shutting down persistent container {self.container_name}...")
            try:
                await self._kill_container()
                self.container_name = None
                self.log("sandbox_shell", "Container removed.")
            except Exception as e:
                self.log("sandbox_shell", f"Error during container shutdown: {e}")
            finally:
                self.container_name = None

    async def run(self, command):
        """Executes a command inside the existing persistent container."""
        if not self.runtime:
            return self.result("Docker or podman not available.", False)

        if not self.container_name:
            return self.result("Sandbox container not initialized.", False)

        timeout_val = self.config.get("execution_timeout", default=10)
        output_limit = self.config.get("output_limit", default=2000)
        safety_timeout = timeout_val + 5

        cmd = [
            self.runtime, 'exec',
            self.container_name,
            'timeout', '-k', '1', '-s', 'KILL', str(timeout_val),
            'sh', '-c', command
        ]

        try:
            stdout, stderr, exit_code, timed_out = await self._run_async_cmd(
                cmd, timeout=safety_timeout, limit=output_limit
            )

            success = True

            stdout_text = stdout.decode('utf-8', errors='replace').strip()
            stderr_text = stderr.decode('utf-8', errors='replace').strip()

            truncated = len(stdout) >= output_limit or len(stderr) >= output_limit

            errors = []

            if timed_out:
                errors.append(f"Command execution timed out after {timeout_val}s")

            if truncated:
                errors.append(f"Output truncated - limit: {output_limit} chars")

            if exit_code == 137:
                errors.append(f"Process forcibly killed")

            results = {
                "stdout": stdout_text,
                "stderr": stderr_text,
                "exit_code": exit_code
            }

            if errors:
                success = False
                results["errors"] = errors

            return self.result(results, success)

        except Exception as e:
            return self.result(f"Error while running sandboxed shell command: {e}", False)

    @core.module.command("shell", send_to_ai=True, help={
        "<cmd>": "runs a command in the sandboxed shell"
    })
    async def cmd_shell(self, args):
        if not args:
            return "Usage: shell <command>"

        command = " ".join(args)
        result = await self.run(command)

        if isinstance(result, dict):
            content = result.get("content")
            if not content:
                return "error getting command output"

            stdout = content.get("stdout")
            stderr = content.get("stderr")
            errors = content.get("errors")

            output = []
            if stdout:
                output.append(stdout)
            if stderr:
                output.append(stderr)

            if errors:
                output.append("errors:\n"+"\n".join(errors))

            return "\n\n".join(output) or "NO OUTPUT"
        return str(result)

    def _get_setup(self):
        return (
            f"Runtime: {self.runtime or 'Not available'}\n"
            f"Container Name: {self.container_name or 'Not running'}\n"
            f"User ID: {self.config.get('run_as_user', default='') or 'Host User'}\n"
            f"Image: {self.config.get('image', default='python:3.11-slim')}\n",
            f"Internet Access: {'enabled' if self.config.get('internet_access') else 'disabled'}\n",
            f"Persistent Data: {self.config.get('persistent_data', default=True)}\n",
            f"gVisor Enabled: {self.use_gvisor}"
        )

    @core.module.command("shell_setup", send_to_ai=True)
    async def cmd_setup(self, args):
        """Show details about your sandbox setup."""
        return self._get_setup()
