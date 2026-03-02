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

class FilesTool(core.tool.Tool):
    async def list_dir(self, path: str) -> dict:
        """
        list the files in a directory.
        """
        try:
            files = os.listdir(os.path.expanduser(path))
        except Exception as e:
            return {"error": e}

        result = []
        for file_name in files:
            file_path = os.path.expanduser(os.path.join(path, file_name))
            file_ext = os.path.splitext(file_name)[-1]
            file_type = "file" if os.path.isfile(file_path) else "directory"

            data = {
                "path": file_path,
                "type": file_type,
                "size": sizeof_format(int(
                    # depends on if it's a file or folder'
                    await get_dir_size(file_path, self.channel) if file_type == "directory" else os.path.getsize(file_path)
                ))
            }

            result.append(data)

        return self.result(result)

    async def _backup_file(self, path: str):
        """backs up a file (within the same directory) using timestamps"""

        if not os.path.exists:
            # dont back up when theres nothing to overwrite
            return False

        await self.channel.announce(f"backing up {path}..")

        timestamp = datetime.datetime.now().strftime("%d%M%Y%H%M%S")
        shutil.copy(path, f"{path}.{timestamp}.old")

        return self.result(True)

    async def create_dir(self, path: str) -> dict:
        """creates a directory. takes an absolute path, will automatically create any directories in the path to it"""

        os.makedirs(path, exist_ok=True)

    async def create_file(self, path: str, body: str) -> dict:
        """create a file with your specified content"""
        if os.path.exists(path):
            return {"error": "file already exists!"}

        open(path, 'w').write(body)

        return self.result(True)

    async def write_file(self, path: str, body: str) -> dict:
        """write to file. always makes a backup for safety."""

        await self.channel.announce(f"writing to file {path}:\n---\n```{body}```\n---\n")

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
        """append to file. always makes a backup for safety."""
        if not os.path.exists(path):
            return self.result("file did not exist", False)

        await self.channel.announce(f"appending to file {path}:\n---\n```{body}```\n---\n")

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
        """moves a file from src_path to target_path. can also be used to rename files. always use absolute paths for both src_path and target_path!"""

        await self.channel.announce(f"mv {src_path} -> {target_path}")

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
        moves multiple files from source to destination.
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
                await self._backup_file(file_data.get("target_path"))
            except Exception as e:
                return {"error": f"error while backing up file: {e}"}

            try:
                shutil.move(file_data['source_path'], file_data['target_path'])
                output = "success"
            except Exception as e:
                output = f"error: {e}"

            result.append([
                    file_data['source_path'],
                    output
            ])

        return self.result(result)

    async def delete_file(self, path: str) -> dict:
        """moves a file to trash. never outright deletes, for safety's sake"""

        trash_path = os.path.join(core.get_data_path(), "trash")
        if not os.path.exists(trash_path):
            os.mkdir(trash_path)

        await self.channel.announce(f"trashing file {path}")

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
        """returns a list of all files in the trash folder"""

        return self.result(
            os.listdir(
                os.path.join(core.get_data_path(), "trash")
            )
        )

    async def empty_trash(self) -> dict:
        """empties the trash folder. use with caution!"""
        trash_path = os.path.join(core.get_data_path(), "trash")

        for file in os.listdir(trash_path):
            if os.path.isdir(os.path.join(trash_path, file)):
                shutil.rmtree(os.path.join(trash_path, file))
            else:
                os.remove(os.path.join(trash_path, file))

        return self.result(True)
