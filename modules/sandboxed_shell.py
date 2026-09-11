import asyncio
import hashlib
import json
import os
import shutil
import signal
import sys

import core


class SandboxedShell(core.module.Module):
    """
    Lets your AI safely run shell commands in a persistent sandboxed docker/podman container
    """

    header = "Shell"

    settings = {
        "internet_access": {
            "default": True,
            "description": "Whether the sandbox container has access to the internet"
        },
        "persistent_data": {
            "default": True,
            "description": "When on, the home folder inside the sandbox is persistent and mapped to the folder you specify. When off, it's a temporary folder in RAM (tmpfs)"
        },
        "sandbox_path": {
            "default": "~/sandbox",
            "description": "The path to the folder your shell will be limited to. It can't access anything outside this folder!",
            "depends": {"persistent_data": True}
        },
        "temporary_filesystem_size_limit": {
            "default": "512m",
            "description": "Maximum size for the temporary sandbox disk (e.g., 512m, 2g)",
            "depends": {"persistent_data": False}
        },
        "execution_timeout": {
            "default": 30,
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
            "default": 200,
            "description": "Maximum amount of processes to allow"
        },
        "method": {
            "default": "dockerfile",
            "type": "select",
            "options": {
                "dockerfile": "Use a dockerfile to set up your container. A default dockerfile is provided, but you can point this at any dockerfile on your filesystem",
                "image": "Use a docker container image (such as from https://hub.docker.com/)"
            }
        },
        "dockerfile_path": {
            "default": "modules/sandboxed_shell/Dockerfile",
            "description": "Path to a Dockerfile to build a custom image from.",
            "depends": {"method": "dockerfile"}
        },
        "image": {
            "default": "debian:stable-slim",
            "description": "Container image to use for the sandbox",
            "depends": {"method": "image"}
        },
        "run_as_user": {
            "default": "",
            "description": "User ID to run the container processes as. Defaults to your current host user's uid for safe file ownership."
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

    async def _build_image(self, force=False):
        """Builds a Docker image from the configured Dockerfile.
        
        Args:
            force: If True, always build regardless of hash match.
        """
        if self.config.get("method") != "dockerfile":
            self.log("sandbox_shell", "Not using dockerfile method, skipping build.")
            return None

        dockerfile_path = self.config.get("dockerfile_path")
        if not dockerfile_path:
            self.log("sandbox_shell", "No dockerfile_path configured.")
            return None

        img_name = "openlumara_sandbox"
        img_tag = "latest"
        full_image = f"{img_name}:{img_tag}"

        # expand user home dir if present
        dockerfile_path = os.path.expanduser(dockerfile_path)

        # if path is relative to openlumara root, find the root
        if not os.path.isabs(dockerfile_path):
            # try to find openlumara root by checking if it's relative to this module
            module_dir = os.path.dirname(os.path.abspath(__file__))
            candidate = os.path.join(module_dir, '..', '..', dockerfile_path)
            if os.path.isfile(candidate):
                dockerfile_path = os.path.abspath(candidate)

        if not os.path.isfile(dockerfile_path):
            self.log("sandbox_shell", f"Dockerfile not found at {dockerfile_path}, skipping build.")
            return None

        # compute current hash
        current_hash = self._get_dockerfile_hash(dockerfile_path)
        stored_hash = self._load_image_hash()

        if not force and stored_hash == current_hash:
            # check if image exists
            try:
                stdout, _, _, _ = await self._run_async_cmd(
                    [self.runtime, 'images', '--format', '{{.Repository}}:{{.Tag}}', full_image],
                    timeout=5.0, limit=256
                )
                if full_image in stdout.decode('utf-8'):
                    self.log("sandbox_shell", f"Image {full_image} is up to date (hash unchanged), skipping build.")
                    return full_image
            except Exception:
                pass

        if force:
            self.log("sandbox_shell", f"Force rebuild requested for {dockerfile_path}")
        elif stored_hash != current_hash:
            self.log("sandbox_shell", f"Dockerfile changed, rebuilding image {full_image}")

        use_buildx = shutil.which("buildx") is not None

        if use_buildx:
            self.log("sandbox_shell", "Using BuildKit (buildx) for image build.")
            build_env = os.environ.copy()
            build_env["DOCKER_BUILDKIT"] = "1"
        else:
            self.log("sandbox_shell", "buildx not found, using legacy builder.")
            build_env = os.environ.copy()

        uid = self.config.get("run_as_user") or self.host_user_uid
        gid = self.config.get("run_as_user") or self.host_user_gid

        try:
            if sys.platform == "win32":
                process = await asyncio.create_subprocess_exec(
                    self.runtime, 'build', '--build-arg', f"UID={uid}", '--build-arg', f"GID={uid}", '-t', full_image, '-f', dockerfile_path, '.',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=build_env
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    self.runtime, 'build', '--build-arg', f"UID={uid}", '--build-arg', f"GID={uid}", '-t', full_image, '-f', dockerfile_path, '.',
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    preexec_fn=os.setsid,
                    env=build_env
                )

            stdout_lines = []
            timed_out = False
            try:
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_text = line.decode('utf-8', errors='replace').strip()
                    if line_text:
                        stdout_lines.append(line_text)
                        self.log("sandbox_shell", f"[build] {line_text}")
            except asyncio.TimeoutError:
                timed_out = True
                await self._kill_process_tree(process)

            await process.wait()
            exit_code = process.returncode if process.returncode is not None else -1

            if exit_code != 0:
                self.log("sandbox_shell", f"Image build failed (exit code {exit_code})")
                for line in stdout_lines[-20:]:
                    self.log("sandbox_shell", f"[build] {line}")
                return None

            # save the hash after successful build
            self._save_image_hash(current_hash)
            self.log("sandbox_shell", f"Image {full_image} built successfully.")
            return full_image

        except Exception as e:
            self.log("sandbox_shell", f"Error building image: {e}")
            return None

    async def _start_container(self):
        """Starts the persistent sandbox container."""
        if not self.runtime:
            return

        method = self.config.get("method", default="dockerfile")
        dockerfile_path = self.config.get("dockerfile_path")
        img = self.config.get("image", default="debian:stable-slim")

        if method == "dockerfile":
            if dockerfile_path:
                built_image = await self._build_image()
                if built_image:
                    img = built_image
                else:
                    self.log("sandbox_shell", "Build failed, using default image.")
            else:
                self.log("sandbox_shell", "No dockerfile_path set, using default image.")

        elif method == "image":
            self.log("sandbox_shell", f"Using image method with: {img}")
        else:
            self.log("sandbox_shell", f"Unknown method: {method}, using default image.")

        # check if container already exists and is running
        try:
            stdout, _, _, _ = await self._run_async_cmd(
                [self.runtime, 'ps', '--format', '{{.Names}}', '--filter', f'name={self.container_name}'],
                timeout=5.0, limit=256
            )
            if self.container_name in stdout.decode('utf-8'):
                self.log("sandbox_shell", f"Container {self.container_name} already running.")
                return
        except Exception:
            pass

        # remove any leftover container with the same name
        try:
            await self._run_async_cmd(
                [self.runtime, 'rm', '-f', self.container_name],
                timeout=10.0
            )
        except Exception:
            pass

        uid = self.config.get("run_as_user") or self.host_user_uid
        gid = self.config.get("run_as_user") or self.host_user_gid

        # --rm: if the container ever dies (e.g. OOM from a resource exhaustion attack),
        # docker removes it automatically so we can cleanly start a fresh one.
        # Persistence is unaffected: installed packages live in the image, and files
        # live in the sandbox folder mount.
        cmd = [self.runtime, 'run', '-d', '--rm', '--init', '--name', self.container_name]

        if self.use_gvisor:
            cmd.extend(['--runtime', 'runsc'])
            if self.runtime == "podman":
                cmd.extend(["--runtime-flag", "ignore-cgroups"])

        cmd.extend([
            '--user', f"{uid}:{gid}",
            '--cap-drop', 'ALL',
            '--cap-add', 'KILL',
            '--read-only',
            '--security-opt', 'no-new-privileges:true',
            '--cpus', str(self.config.get("cpu_limit", default=0.5)),
            '--memory', self.config.get("memory_limit", default="512m"),
            '--pids-limit', str(self.config.get("max_processes", default=10)),
            '--network', 'bridge' if self.config.get("internet_access", default=False) else 'none',
            '--stop-timeout', '1'
        ])

        home_dir = "/home/lumara"
        dockerfile_mount = f"{home_dir}/Dockerfile"

        if self.config.get("persistent_data", default=True):
            selinux_flag = ":Z" if sys.platform != "win32" else ""
            cmd.extend(['-v', f"{self.host_workspace}:{home_dir}{selinux_flag}"])
        else:
            limit = self.config.get("temporary_filesystem_size_limit", default="512m")
            cmd.extend(['--tmpfs', f"{home_dir}:size={limit}"])

        # mount dockerfile read-only if using dockerfile method
        if method == "dockerfile" and dockerfile_path:
            expanded_path = os.path.expanduser(dockerfile_path)
            if not os.path.isabs(expanded_path):
                module_dir = os.path.dirname(os.path.abspath(__file__))
                expanded_path = os.path.abspath(os.path.join(module_dir, '..', '..', expanded_path))
            if os.path.isfile(expanded_path):
                cmd.extend(['-v', f"{expanded_path}:{dockerfile_mount}:ro"])
                self.log("sandbox_shell", f"Mounted Dockerfile read-only at {dockerfile_mount}")

        cmd.extend(['-w', home_dir, img])

        self.log(self.name, "starting using command: "+' '.join(cmd))

        try:
            stdout, stderr, exit_code, _ = await self._run_async_cmd(cmd, timeout=30.0, limit=1024 * 1024)
            if stderr:
                self.log("sandbox_shell", f"ERROR: {stderr}")
                self.container_name = None
                return

            self.log("sandbox_shell", f"Container {self.container_name} started (UID: {uid}, Image: {img}, method: {method}).")
        except Exception as e:
            self.log("sandbox_shell", f"Error starting container: {e}")
            self.container_name = None

    async def _is_container_running(self):
        """Checks whether the sandbox container currently exists and is running."""
        if not self.runtime or not self.container_name:
            return False
        try:
            stdout, _, _, _ = await self._run_async_cmd(
                [self.runtime, 'ps', '--format', '{{.Names}}', '--filter', f'name={self.container_name}'],
                timeout=5.0, limit=256
            )
            return self.container_name in stdout.decode('utf-8')
        except Exception:
            return False

    async def _stop_container(self):
        """Stops and removes the container."""
        if self.container_name:
            try:
                await self._run_async_cmd([self.runtime, 'stop', self.container_name], timeout=10.0)
            except Exception:
                pass
            try:
                await self._run_async_cmd([self.runtime, 'rm', '-f', self.container_name], timeout=10.0)
            except Exception:
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

    def _get_dockerfile_hash(self, path):
        """Compute md5 hash of a dockerfile for change detection."""
        md5 = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                md5.update(chunk)
        return md5.hexdigest()

    def _load_image_hash(self):
        """Load the stored hash of the last built dockerfile."""
        try:
            with open(self.image_hash_path, 'r') as f:
                return f.read().strip()
        except (FileNotFoundError, IOError):
            return None

    def _save_image_hash(self, hash_val):
        """Save the hash of the currently built dockerfile."""
        try:
            os.makedirs(os.path.dirname(self.image_hash_path), exist_ok=True)
            with open(self.image_hash_path, 'w') as f:
                f.write(hash_val)
        except IOError as e:
            self.log("sandbox_shell", f"Failed to save image hash: {e}")

    async def on_ready(self):
        """Starts the persistent container when the module is ready."""
        self.runtime = None
        self.container_name = None
        self.use_gvisor = False
        self.container_name = "openlumara_shell"

        # hash tracking file location
        self.image_hash_path = core.get_data_path(os.path.join("sandboxed_shell", "docker_image_hash"))

        if shutil.which("podman"):
            self.runtime = "podman"
        elif shutil.which("docker"):
            self.runtime = "docker"

        if not self.runtime:
            self.log("sandbox_shell", "Neither docker nor podman are available!")
            return

        self.host_workspace = core.get_path(
            os.path.expanduser(self.config.get("sandbox_path", default="~/sandbox"))
        )
        os.makedirs(self.host_workspace, exist_ok=True)

        # resolve host user uid for safe file ownership
        self.host_user_uid = os.getuid()
        self.host_user_gid = os.getgid()

        if shutil.which("runsc"):
            self.use_gvisor = True
            self.log("sandbox_shell", "gVisor (runsc) detected. Sandbox will use gVisor for enhanced security.")
        else:
            self.log("sandbox_shell", "Warning: gVisor (runsc) not found. Sandbox is running with standard isolation.")

        await self._start_container()

    async def on_shutdown(self):
        """Stops and removes the container when the application shuts down."""
        if self.container_name and self.runtime:
            self.log("sandbox_shell", f"Shutting down container {self.container_name}...")
            try:
                await self._stop_container()
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

        # the container can die at any time (e.g. OOM from a resource exhaustion attack).
        # with --rm it's removed on death, so just start a fresh one.
        if not await self._is_container_running():
            self.log("sandbox_shell", "Container is not running, restarting it.")
            await self._start_container()
            if not await self._is_container_running():
                return self.result("Sandbox container crashed and could not be restarted.", False)

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
        gid = self.config.get('run_as_user') or self.host_user_gid
        method = self.config.get('method', default='dockerfile')
        lines = [
            f"Runtime: {self.runtime or 'Not available'}",
            f"Container Name: {self.container_name or 'Not running'}",
            f"method: {method}",
            f"Internet Access: {'enabled' if self.config.get('internet_access') else 'disabled'}",
            f"Persistent Data: {self.config.get('persistent_data', default=True)}",
            f"gVisor Enabled: {self.use_gvisor}"
        ]
        if method == "dockerfile":
            dockerfile_path = self.config.get('dockerfile_path')
            if dockerfile_path:
                expanded = os.path.expanduser(dockerfile_path)
                if not os.path.isabs(expanded):
                    module_dir = os.path.dirname(os.path.abspath(__file__))
                    expanded = os.path.abspath(os.path.join(module_dir, '..', '..', expanded))
                exists = "exists" if os.path.isfile(expanded) else "NOT FOUND"
                lines.append(f"Dockerfile: {dockerfile_path} ({exists})")
            else:
                lines.append("Dockerfile: (not set)")
        elif method == "image":
            lines.append(f"Image: {self.config.get('image')}")
        return "\n".join(lines)

    @core.module.command("shell_setup", send_to_ai=True)
    async def cmd_setup(self, args):
        """Show details about your sandbox setup."""
        return self._get_setup()

    @core.module.command("shell_build", send_to_ai=True, help={
        "": "rebuilds the sandbox image from the configured Dockerfile"
    })
    async def cmd_build(self, args):
        """Build or rebuild the sandbox image from the Dockerfile."""
        if not self.runtime:
            return "Docker or podman not available."

        method = self.config.get("method", default="dockerfile")
        if method != "dockerfile":
            return "Not using dockerfile method. Switch to 'dockerfile' in module config to use this command."

        dockerfile_path = self.config.get("dockerfile_path")
        if not dockerfile_path:
            return "No Dockerfile configured. Set 'dockerfile_path' in module config."

        built_image = await self._build_image(force=True)
        if built_image:
            # restart container with the new image
            await self._stop_container()
            await self._start_container()
            return "Image rebuilt successfully. Container restarted with new image."
        else:
            return "Image build failed. Check logs for details."
