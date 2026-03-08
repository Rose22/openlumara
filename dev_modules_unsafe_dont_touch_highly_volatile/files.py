import core
import os
import shutil
import pathlib
import datetime

async def get_dir_size(start_path, channel):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            # skip if it is symbolic link
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)

    return total_size

def sizeof_format(num, suffix="B"):
    for unit in ("", "K", "M", "G", "T", "P", "E", "Z"):
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"

class Files(core.module.Module):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sandbox_path = os.path.abspath(core.config.get("sandbox_folder"))
        if not os.path.exists(self.sandbox_path):
            os.mkdir(self.sandbox_path)

    def _get_path(self, path: str):
        # remove the sandbox path from it in case the AI inserts it
        path = path.replace(self.sandbox_path, "")

        # remove / at the beginning and end
        path = path.strip("/")

        # prevent path traversal
        combined_path = os.path.join(self.sandbox_path, path)
        real_path = os.path.abspath(combined_path)

        if not real_path.startswith(self.sandbox_path + os.path.sep) and real_path != self.sandbox_path:
            raise ValueError(f"Access denied: target path is outside the sandbox!")


        return path

    async def list_dir(self, path: str) -> dict:
        """
        List the files inside the sandbox (/ = sandbox root)
        Use relative paths from sandbox root
        """
        dir_path = self._get_path(path)

        try:
            files = os.listdir(dir_path)
        except Exception as e:
            return {"error": e}

        result = []
        for file_name in files:
            file_path = os.path.join(dir_path, file_name)

            file_ext = os.path.splitext(file_name)[-1]
            file_type = "file" if os.path.isfile(file_path) else "directory"

            size_bytes = 0
            if file_type == "directory":
                size_bytes = await get_dir_size(file_path, self.manager.channel)
            else:
                size_bytes = os.path.getsize(file_path)

            data = {
                "path": file_path,
                "type": file_type,
                "size": sizeof_format(int(size_bytes))
            }

            result.append(data)

        return self.result(result)

    async def _backup_file(self, path: str):
        """Backs up a file (within the same directory) using timestamps"""

        path = self._get_path(path)
        if not os.path.exists(path):
            # dont back up when theres nothing to overwrite
            return False

        await self.manager.channel.announce(f"backing up {path}..")

        timestamp = datetime.datetime.now().strftime("%d%M%Y%H%M%S")
        shutil.copy(path, f"{path}.{timestamp}.old")

        return self.result(True)

    async def create_dir(self, path: str) -> dict:
        """Creates a directory inside the sandbox. Will automatically create any directories in the path to it"""

        path = self._get_path(path)
        os.makedirs(path, exist_ok=True)

    async def create_file(self, path: str, body: str) -> dict:
        """create a file with your specified content"""
        path = self._get_path(path)
        if os.path.exists(path):
            return {"error": "file already exists!"}

        open(path, 'w').write(body)

        return self.result(True)

    async def write_file(self, path: str, body: str) -> dict:
        """Write to file inside the sandbox. Use relative paths from the sandbox root (/). Always makes a backup for safety."""

        path = self._get_path(path)
        await self.manager.channel.announce(f"writing to file {path}:\n---\n```{body}```\n---\n")

        # first, make a backup
        try:
            await self._backup_file(path)
        except Exception as e:
            return {"error": f"error while backing up file: {e}"}

        try:
            open(path, 'w').write(body)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def append_to_file(self, path: str, body: str) -> dict:
        """Append to file inside the sandbox. Use relative paths from the sandbox root (/). Always makes a backup for safety."""
        path = self._get_path(path)
        if not os.path.exists(path):
            return self.result("file did not exist", False)

        await self.manager.channel.announce(f"appending to file {path}:\n---\n```{body}```\n---\n")

        # first, make a backup
        try:
            await self._backup_file(path)
        except Exception as e:
            return {"error": f"error while backing up file: {e}"}

        try:
            with open(path, 'a') as f:
                f.write("\n"+body)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def move_file(self, src_path: str, target_path: str) -> dict:
        """Moves a file from src_path to target_path. Can also be used to rename files. Use relative paths from the sandbox root (/)"""

        await self.manager.channel.announce(f"mv {src_path} -> {target_path}")

        src_path = self._get_path(src_path)
        taget_path = self._get_path(target_path)

        # first, make a backup
        try:
            await self._backup_file(target_path)
        except Exception as e:
            return self.result(f"error while backing up file: {e}", False)

        try:
            shutil.move(src_path, target_path)
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def move_multiple_files(self, list_of_moves: list) -> dict:
        """
        Moves multiple files from source to destination.
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
                await self._backup_file(self._get_path(file_data.get("target_path")))
            except Exception as e:
                return {"error": f"error while backing up file: {e}"}

            try:
                shutil.move(self._get_path(file_data['source_path']), self._get_path(file_data['target_path']))
                output = "success"
            except Exception as e:
                output = f"error: {e}"

            result.append([
                    self._get_path(file_data['source_path']),
                    output
            ])

        return self.result(result)

    async def delete_file(self, path: str) -> dict:
        """Moves a file to trash. Never outright deletes, for safety's sake"""

        path = self._get_path(path)
        trash_path = os.path.join(core.get_data_path(), "trash")
        if not os.path.exists(trash_path):
            os.mkdir(trash_path)

        await self.manager.channel.announce(f"trashing file {path}")

        try:
            dest_path = os.path.join(trash_path, os.path.basename(path))
            if not os.path.exists(dest_path):
                shutil.move(path, dest_path)
            else:
                timestamp = datetime.datetime.now().strftime("%d%M%Y%H%M%S")
                shutil.copy(dest_path, f"{path}.{timestamp}.old")
            return self.result(True)
        except Exception as e:
            return self.result(e, False)

    async def get_trash_contents(self) -> dict:
        """Returns a list of all files in the trash folder"""

        return self.result(
            os.listdir(
                os.path.join(core.get_data_path(), "trash")
            )
        )

    async def empty_trash(self) -> dict:
        """Empties the trash folder. Use with caution!"""
        trash_path = os.path.join(core.get_data_path(), "trash")

        for file in os.listdir(trash_path):
            if os.path.isdir(os.path.join(trash_path, file)):
                shutil.rmtree(os.path.join(trash_path, file))
            else:
                os.remove(os.path.join(trash_path, file))

        return self.result(True)
