import core
import os
import sys
import asyncio
import aiofiles
import urllib
import shutil
import datetime
import glob

async def _run_sync(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)

async def get_dir_size(start_path, channel):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path, followlinks=False):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += await asyncio.os.path.getsize(fp)

    return total_size

def sizeof_format(num, suffix="B"):
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

class Files(core.module.Module):
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    MAX_GLOB_DEPTH = 10
    MAX_SEARCH_RESULTS = 50

    settings = {
        "sandbox_folder": "sandbox"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sandbox_path = os.path.realpath(os.path.expanduser(self.config.get("sandbox_folder")))
        self.trash_path = os.path.realpath(os.path.join(core.get_data_path(), "trash"))

        if not os.path.exists(self.sandbox_path):
            os.makedirs(self.sandbox_path, exist_ok=True)
        if not os.path.exists(self.trash_path):
            os.makedirs(self.trash_path, exist_ok=True)

    def _validate_absolute_path(self, abs_path: str) -> str | None:
        """
        Validate that an absolute path is within the sandbox.
        Returns the relative path if valid, None if invalid.
        Reuses the same validation logic as _get_sandbox_path.
        """
        try:
            real_path = os.path.realpath(abs_path)
        except (OSError, ValueError):
            return None

        if os.path.islink(abs_path):
            return None

        sandbox_prefix = self.sandbox_path + os.path.sep

        if sys.platform == "win32":
            check_path = real_path.lower()
            check_prefix = sandbox_prefix.lower()
        else:
            check_path = real_path
            check_prefix = sandbox_prefix

        if check_path.startswith(check_prefix) or check_path == self.sandbox_path:
            return self._strip_sandbox_path(real_path)

        return None

    def _get_sandbox_path(self, target_path: str):
        path = target_path

        # remove path separator at the beginning and end
        path = path.strip(os.path.sep)

        # remove the sandbox path from it in case the AI inserts it
        path = self._strip_sandbox_path(path)

        # basic path traversal prevention
        decoded = path
        for _ in range(3):  # Handle double/triple encoding
            decoded = urllib.parse.unquote(decoded)

        if ".." in decoded or "\x00" in decoded:
            raise ValueError("Path traversal is not allowed")

        # block symlink paths
        if hasattr(os, 'O_NOFOLLOW'):
            # check if any component is a symlink
            parts = path.split(os.path.sep)
            for i, part in enumerate(parts):
                if i == 0:
                    continue  # Skip root
                test_path = os.path.join(self.sandbox_path, *parts[:i])
                if os.path.islink(test_path):
                    raise ValueError("Symlinks are not allowed inside the sandbox")

        if not path:
            return self.sandbox_path

        # more path traversal protection
        path_in_sandbox = os.path.join(self.sandbox_path, os.path.normpath(path))
        validated = self._validate_absolute_path(path_in_sandbox)

        if validated is None:
            raise ValueError("Access denied: target path is outside sandbox")

        return os.path.join(self.sandbox_path, validated)

    def _strip_sandbox_path(self, path: str):
        prefix = self.sandbox_path + os.sep
        if path.startswith(prefix):
            return path[len(prefix):]
        elif path == self.sandbox_path:
            return ""
        return path

    async def list_dir(self, path: str) -> dict:
        """
        List the files inside the sandbox.
        Use relative paths.
        """
        dir_path = self._get_sandbox_path(path)

        try:
            files = os.listdir(dir_path)
        except Exception as e:
            return self.result(f"error: {e}", False)

        result = []
        for file_name in files:
            file_path = os.path.join(dir_path, file_name)

            file_ext = os.path.splitext(file_name)[-1]
            file_type = "file" if os.path.isfile(file_path) else "directory"

            size_bytes = 0
            if file_type == "directory":
                try:
                    # run filesize check asynchronously
                    size_bytes = await get_dir_size(file_path, self.channel)
                except:
                    size_bytes = -1
            else:
                size_bytes = os.path.getsize(file_path)

            data = {
                "path": self._strip_sandbox_path(file_path),
                "type": file_type,
                "size": sizeof_format(int(size_bytes))
            }

            result.append(data)

        return self.result(result)

    async def _backup_file(self, path: str):
        """Backs up a file (within the same directory) using timestamps"""

        safe_path = self._get_sandbox_path(path)
        if not os.path.exists(safe_path):
            # dont back up when theres nothing to overwrite
            return False

        timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        await _run_sync(shutil.copy, safe_path, f"{safe_path}.{timestamp}.old")

        return self.result(True)

    async def create_dir(self, path: str) -> dict:
        """Creates a directory inside the sandbox. Will automatically create any directories in the path to it. Use relative paths."""

        safe_path = self._get_sandbox_path(path)
        os.makedirs(safe_path, exist_ok=True)

        return self.result(True)

    async def create(self, path: str, body: str) -> dict:
        """Create a file with your specified content. Use relative paths."""
        safe_path = self._get_sandbox_path(path)

        if os.path.exists(safe_path):
            return self.result(f"error: file already exists!", False)

        if len(body) > self.MAX_FILE_SIZE:
            return self.result("error: file too large", False)

        try:
            # O_EXCL makes sure it wont overwrite
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW

            fd = os.open(safe_path, flags, mode=0o644)
        except OSError as e:
            return self.result(f"Error creating file: {e}", False)

        async with aiofiles.open(fd, 'w') as f:
            await f.write(body)

        return self.result(True)

    async def read(self, path: str):
        """Reads a file inside the sandbox. Use relative paths."""
        safe_path = self._get_sandbox_path(path)
        try:
            if not os.path.isfile(safe_path):
                 return self.result("error: not a file")

            flags = os.O_RDONLY
            # dont follow symlinks
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW

            fd = os.open(safe_path, flags)
            async with aiofiles.open(fd, 'r') as f:
                content = await f.read()
            return self.result(content)
        except Exception as e:
            return self.result(f"error: {e}")

    async def write(self, path: str, body: str) -> dict:
        """Write to file inside the sandbox. Use relative paths. Always makes a backup for safety."""
        safe_path = self._get_sandbox_path(path)

        if len(body) > self.MAX_FILE_SIZE:
            return self.result("error: file too large", False)

        try:
            await self._backup_file(safe_path)
        except Exception as e:
            return self.result(f"error while backing up file: {e}", False)

        try:
            # O_WRONLY: Open for writing only
            # O_CREAT: Create file if it doesn't exist
            # O_TRUNC: Truncate file to 0 bytes
            # O_NOFOLLOW: Do not follow symlinks
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            if hasattr(os, 'O_NOFOLLOW'):
                flags |= os.O_NOFOLLOW

            fd = os.open(safe_path, flags, mode=0o644)
            async with aiofiles.open(fd, 'w') as f:
                await f.write(body)
            return self.result(True)
        except OSError as e:
             # happens if O_NOFOLLOW fails (is link) or permissions
            return self.result(f"error: {e}", False)
        except Exception as e:
            return self.result(e, False)

    async def append(self, path: str, body: str) -> dict:
        """Append to file inside the sandbox. Use relative paths. Always makes a backup for safety."""
        safe_path = self._get_sandbox_path(path)

        if not os.path.exists(safe_path):
            return self.result("file did not exist", False)

        if len(body) > self.MAX_FILE_SIZE:
            return self.result("error: file too large", False)

        try:
            await self._backup_file(safe_path)
        except Exception as e:
            return self.result(f"error while backing up file: {e}", False)

        try:
            flags = os.O_WRONLY | os.O_APPEND
            if hasattr(os, 'O_NOFOLLOW'):
                # dont follow symlinks
                flags |= os.O_NOFOLLOW

            fd = os.open(safe_path, flags, mode=0o644)
            async with aiofiles.open(fd, 'a') as f:
                await f.write("\n" + body)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def move(self, src_path: str, target_path: str) -> dict:
        """Moves a file from src_path to target_path. Can also be used to rename files. Use relative paths."""
        src = self._get_sandbox_path(src_path)
        tgt = self._get_sandbox_path(target_path)

        try:
            await self._backup_file(tgt)
        except Exception as e:
            return self.result(f"error while backing up file: {e}", False)

        try:
            await _run_sync(shutil.move, src, tgt)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def move_multiple(self, list_of_moves: list) -> dict:
        """
        Moves multiple files from source to destination. Use relative paths!
        list_of_moves is structured as such:
        [
            {
                source_path: "source path",
                target_path: "target path"
            },
            {
                source_path: "source path",
                target_path: "target path"
            },
            {
                source_path: "source path",
                target_path: "target path"
            },
        ]

        and so on
        """

        result = []
        for file_data in list_of_moves:
            # first, make a backup
            try:
                await self._backup_file(self._get_sandbox_path(file_data.get("target_path")))
            except Exception as e:
                return self.result(f"error while backing up file: {e}")

            src_path = self._get_sandbox_path(file_data["source_path"])
            tgt_path = self._get_sandbox_path(file_data["target_path"])
            try:
                await _run_sync(shutil.move, src_path, tgt_path)
                output = "success"
            except Exception as e:
                output = f"error: {e}"

            result.append([
                    src_path,
                    output
            ])

        return self.result(result)

    async def delete(self, path: str) -> dict:
        """Moves a file to trash. Never outright deletes, for safety's sake"""
        safe_path = self._get_sandbox_path(path)

        try:
            base_name = os.path.basename(safe_path)
            dest_path = os.path.join(self.trash_path, base_name)

            if not os.path.exists(dest_path):
                target = dest_path
            else:
                timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
                target = f"{dest_path}.{timestamp}"

            await _run_sync(shutil.move, safe_path, target)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def get_trash_contents(self) -> dict:
        """Returns a list of all files in the trash folder"""

        return self.result(
            os.listdir(self.trash_path)
        )

    async def empty_trash(self) -> dict:
        """Empties the trash folder. Use with caution!"""
        def _clear():
            for file in os.listdir(self.trash_path):
                fpath = os.path.join(self.trash_path, file)
                try:
                    if os.path.isdir(fpath):
                        shutil.rmtree(fpath)
                    else:
                        os.remove(fpath)
                except:
                    pass

        await _run_sync(_clear)
        return self.result(True)

    async def search_files(self, pattern: str, recursive: bool = False) -> dict:
        """Search for files matching a glob pattern inside the sandbox."""

        if not pattern or not pattern.strip():
            return self.result("error: empty pattern", False)

        decoded = pattern
        for _ in range(3):
            decoded = urllib.parse.unquote(decoded)

        if ".." in decoded or "\x00" in decoded:
            return self.result("error: path traversal not allowed", False)

        if os.path.isabs(pattern):
            return self.result("error: absolute paths not allowed", False)

        if recursive and pattern.count("**") > self.MAX_GLOB_DEPTH:
            return self.result(f"error: max recursion depth is {self.MAX_GLOB_DEPTH}", False)

        if "*" not in pattern and "?" not in pattern and len(pattern) >= 3:
            # default to fuzzy search
            pattern = f"*{pattern}*"

        full_pattern = os.path.join(self.sandbox_path, pattern)
        try:
            matches = glob.glob(full_pattern, recursive=recursive)
        except Exception as e:
            return self.result(f"error during search: {e}", False)

        # filter results
        safe_matches = []
        for match in matches:
            rel_path = self._validate_absolute_path(match)
            if rel_path:
                safe_matches.append(rel_path)
            if len(safe_matches) >= self.MAX_SEARCH_RESULTS:
                break

        return self.result({
            "matches": sorted(safe_matches),
            "truncated": len(matches) > self.MAX_SEARCH_RESULTS
        })
