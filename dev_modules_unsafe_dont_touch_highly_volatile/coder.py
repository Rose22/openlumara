import core
import os
import sys
import subprocess
import stat
import shutil

class Coder(core.module.Module):
    """
    possibly very unsafe, but allows the AI to create entire code projects in a way that's seperate from your main filesystem.
    can be used to create simple apps on the fly and run them
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.path = core.get_path(os.path.join("data","coder"))

    def _sanitize_path(self, path: str):
        path = path.replace("..", "")
        path = path.replace("./", "")
        path = path.lstrip("/")
        return path

    def _get_project_path(self, name: str):
        """returns the project path as a string"""

        return core.get_path(
            os.path.join(self.path, self._sanitize_path(name))
        )

    def _get_file_path(self, project_name: str, file_path: list):
        """returns the path to a file in the project as a string"""

        file_path_str = self._sanitize_path(os.path.join(*file_path))
        joint_path_str = os.path.join(self._get_project_path(project_name), file_path_str)
        return joint_path_str

    async def list_projects(self):
        return self.result(os.listdir(self.path))

    async def create_project(self, project_name: str, file_structure: dict):
        """
        creates an entire project structure in one go!

        for the structure, use a dict like:
        {
            "root": ["main.py", "test.py"],
            "src": {
                "libs": [
                    "mylib.py",
                    "core.py"
                ]
            }
        }
        """
        async def _build_structure(current_path: str, structure: dict):
            for name, content in structure.items():
                # Determine the target path. If the key is 'root', we treat it
                # as the current directory itself, not a new subdirectory.
                if name == "root":
                    target_path = current_path
                else:
                    target_path = os.path.join(current_path, name)

                if isinstance(content, dict):
                    # If content is a dict, it represents a directory.
                    os.makedirs(target_path, exist_ok=True)
                    await self.manager.channel.announce(f"Created directory: {target_path}")
                    await _build_structure(target_path, content)
                elif isinstance(content, list):
                    # If content is a list, it represents files in a directory.
                    # Ensure the directory exists (vital for the 'root' case).
                    os.makedirs(target_path, exist_ok=True)
                    for filename in content:
                        file_path = os.path.join(target_path, filename)
                        # Create an empty file (or overwrite existing).
                        with open(file_path, "w") as f:
                            pass
                        await self.manager.channel.announce(f"Created file: {file_path}")

        # Define the base path for the project
        base_path = self._get_project_path(project_name)

        try:
            os.makedirs(base_path, exist_ok=True)
            await self.manager.channel.announce(f"Initializing project: {project_name} at {base_path}")
            await _build_structure(base_path, file_structure)
            await self.manager.channel.announce("Project structure creation complete.")
        except OSError as e:
            await self.manager.channel.announce(f"Error creating project structure: {e}")

    async def read_file(self, project_name: str, file_path: list):
        """
        reads a file within a project.

        use this before editing a file if you don't already have it in memory!

        Args:
            project_name: project name
            file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        with open(file_path_str, "r") as f:
            result = f.read()

        return self.result(result)

    async def edit_file(self, project_name: str, file_path: list, content: str):
        """
        edits a file within a project

        make sure to ALWAYS put a shebang at the top of a script! example: #!interpreter [arguments]

        Args:
            project_name: project name
            file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
            content: the new content of the file
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        with open(file_path_str, "w") as f:
            f.write(content)

        return self.result(True)

    async def execute(self, project_name: str, file_path: list):
        """
        executes a file within a project. will automatically chmod for you if not done already

        Args:
            project_name: project name
            file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        os.chmod(file_path_str, os.stat(file_path_str).st_mode | stat.S_IEXEC)
        try:
            proc = subprocess.run(file_path_str, shell=False, capture_output=True, text=True)
        except Exception as e:
            return self.result(f"error: {e}", False)
        return self.result(proc.stdout)
