import core
import os
import sys
import platform
import shutil
from pathlib import Path

class FileManager(core.module.Module):
    """Gives your AI full access to your filesystem. CAUTION: Unsafe! Use at your own risk."""

    unsafe = True
    _header = "System info"

    settings = {
        "put_system_info_in_prompt": False
    }

    async def on_end_prompt(self):
        if not self.config.get("put_system_info_in_prompt"):
            return None

        details = {
            "OS": sys.platform,
            "OS release": platform.release(),
            "platform": platform.platform(),
            "architecture": platform.machine() if platform.machine() else "unknown",
            "hostname": platform.node(),
            "home dir": os.path.expanduser("~")
        }

        details_string = ""
        for key, value in details.items():
            details_string += f"{key}: {value}\n"
        details_string = details_string.strip()

        return details_string

    def _verify_path(self, path: str, should_be_dir=False, should_be_file=False):
        """Internal helper to validate path existence and type."""
        success = False
        reason = None
        p = Path(path)

        if not p.exists():
            reason = "path does not exist"
        elif should_be_dir and not p.is_dir():
            reason = "target path is not a directory"
        elif should_be_file and not p.is_file():
            reason = "target path is not a file"

        if not reason:
            success = True

        return {"success": success, "reason": reason}

    async def list(self, path: str):
        verify = self._verify_path(path, should_be_dir=True)
        if not verify.get("success"):
            return self.result(verify.get("reason"), False)

        return os.listdir(path)

    async def read(self, path: str):
        verify = self._verify_path(path, should_be_file=True)
        if not verify.get("success"):
            return self.result(verify.get("reason"), False)

        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.result(content)
        except UnicodeDecodeError:
            return self.result("File is not a valid text file. Try 'read_binary' instead.", False)
        except Exception as e:
            return self.result(str(e), False)

    async def read_binary(self, path: str):
        """Reads a file in binary mode. Useful for images, executables, etc."""
        verify = self._verify_path(path, should_be_file=True)
        if not verify.get("success"):
            return self.result(verify.get("reason"), False)

        try:
            with open(path, 'rb') as f:
                content = f.read()
            return self.result(content)
        except Exception as e:
            return self.result(str(e), False)

    async def _write(self, path: str, content: str, mode: str = 'w'):
        """
        Writes content to a file.
        Mode 'w' overwrites, mode 'a' appends.
        Automatically creates parent directories if they don't exist.
        """
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)

            with open(path, mode, encoding='utf-8') as f:
                f.write(content)
            return self.result(f"Successfully wrote to {path} (mode: {mode})")
        except Exception as e:
            return self.result(str(e), False)

    async def write(self, path: str, content: str):
        """Writes content to a file. Automatically creates parent directories."""
        try:
            return await self._write(path, content, mode='w')
        except Exception as e:
            return self.result(str(e), False)

    async def append(self, path: str, content: str):
        return await self._write(path, content, mode='a')

    async def mkdir(self, path: str):
        """Creates a directory and any necessary parent directories."""
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            return self.result(f"Directory created: {path}")
        except Exception as e:
            return self.result(str(e), False)

    async def remove(self, path: str):
        p = Path(path)
        if not p.exists():
            return self.result("path does not exist", False)

        try:
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
            else:
                return self.result("Path is not a file or directory", False)
            return self.result(f"Successfully removed: {path}")
        except Exception as e:
            return self.result(str(e), False)

    async def move(self, src: str, dst: str):
        try:
            # Ensure destination directory exists
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
            return self.result(f"Moved {src} -> {dst}")
        except Exception as e:
            return self.result(str(e), False)

    async def copy(self, src: str, dst: str):
        try:
            Path(dst).parent.mkdir(parents=True, exist_ok=True)
            if Path(src).is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            return self.result(f"Copied {src} -> {dst}")
        except Exception as e:
            return self.result(str(e), False)

    async def get_info(self, path: str):
        verify = self._verify_path(path)
        if not verify.get("success"):
            return self.result(verify.get("reason"), False)

        try:
            p = Path(path)
            stats = p.stat()
            return self.result({
                "name": p.name,
                "absolute_path": str(p.absolute()),
                "size_bytes": stats.st_size,
                "is_file": p.is_file(),
                "is_dir": p.is_dir(),
                "last_modified": stats.st_mtime,
                "created": stats.st_ctime
            })
        except Exception as e:
            return self.result(str(e), False)
