import core
import os
import sys
import re
import subprocess
import stat
import shutil
import itertools
import asyncio
import modules.files_sandboxed


class Coder(modules.files_sandboxed.SandboxedFiles):
    """Allows your AI to write, edit and test code for you."""

    settings = {
        "allow_code_execution": False,
        "sandbox_folder": "~/coder",
        "enable_progress_messages": False
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.sandbox_path
        self._header = "Coder projects in sandbox"

    async def on_system_prompt(self):
        file_list = os.listdir(self.sandbox_path)
        project_list = []
        for filename in file_list:
            if not os.path.isdir(os.path.join(self.sandbox_path, filename)):
                continue

            project_list.append(filename)

        if not project_list:
            return "No projects yet."

        try:
            return "\n".join(project_list)
        except Exception as e:
            return f"error: {e}", False

    def _get_project_path(self, name: str):
        """returns the project path as a string within the sandbox"""
        return self._get_sandbox_path(name)

    def _get_file_path(self, project_name: str, file_path: list):
        """returns the path to a file in the project as a string within the sandbox"""
        # Join project name and the list of path components into a single relative path
        rel_path = os.path.join(project_name, *file_path)
        return self._get_sandbox_path(rel_path)

    async def list_project(self, project_name: str, depth_limit: int = 3):
        """
        Returns a recursive tree representation of the project structure (directories only).
        Structure: [name, [children]]
        """
        project_path = self._get_project_path(project_name)
        if not os.path.exists(project_path):
            return self.result("project does not exist", False)

        def _build_tree(path, current_depth):
            name = os.path.basename(os.path.normpath(path))
            children = []

            if current_depth < depth_limit:
                try:
                    for entry in os.scandir(path):
                        if entry.is_dir():
                            # Recursively build the list of directory lists
                            children.append(_build_tree(entry.path, current_depth + 1))
                except Exception:
                    # If a directory cannot be read, return the node as is
                    pass

            return [name, children]

        try:
            tree = _build_tree(project_path, 0)
            return self.result(tree)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def list_project_contents(self, project_name: str, sub_path: list = None):
        """
        Lists the immediate contents of a specific path within a project.
        This is non-recursive.
        """
        if sub_path is None:
            sub_path = []

        target_path = self._get_project_path(project_name)
        if sub_path:
            target_path = os.path.join(target_path, *sub_path)

        if not os.path.exists(target_path):
            return self.result("path does not exist", False)
        if not os.path.isdir(target_path):
            return self.result("path is not a directory", False)

        try:
            # os.listdir returns only the immediate entries in the directory
            return self.result(os.listdir(target_path))
        except Exception as e:
            return self.result(f"error: {e}", False)


    async def create_project(self, project_name: str, file_structure: dict):
        """
        Creates an entire project structure in one go!

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
                    if self.config.get("enable_progress_messages"):
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
                        if self.config.get("enable_progress_messages"):
                            await self.manager.channel.announce(f"Created file: {file_path}")

        # Define the base path for the project using the sandboxed path method
        base_path = self._get_project_path(project_name)

        try:
            os.makedirs(base_path, exist_ok=True)
            await self.manager.channel.announce(f"Initializing project: {project_name} at {base_path}")
            await _build_structure(base_path, file_structure)
            await self.manager.channel.announce("Project structure creation complete.")
        except OSError as e:
            await self.manager.channel.announce(f"Error creating project structure: {e}")

    # async def read_file(self, project_name: str, file_path: list):
    #     """
    #     Reads a file within a project.
    #
    #     Use this instead of search() if you don't know what you're looking for.
    #
    #     Args:
    #         project_name: project name
    #         file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
    #     """
    #     file_path_str = self._get_file_path(project_name, file_path)
    #     if not os.path.exists(file_path_str):
    #         return self.result("file does not exist!", False)
    #
    #     with open(file_path_str, "r") as f:
    #         result = f.read()
    #
    #     return self.result(result)

    async def edit_file(self, project_name: str, file_path: list, edits: list = None):
        """
        Edits a file within a project using targeted replacements.

        Args:
            project_name: project name
            file_path: path to the file, as a list
            edits: list of dicts, e.g., [{"old_text": "...", "new_text": "..."}]
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        try:
            # 1. Read file and handle BOM (Byte Order Mark)
            with open(file_path_str, 'rb') as f:
                raw_bytes = f.read()

            bom = b''
            if raw_bytes.startswith(b'\xef\xbb\xbf'):
                bom = b'\xef\xbb\xbf'
                content = raw_bytes[len(bom):].decode('utf-8')
            else:
                content = raw_bytes.decode('utf-8')

            # 2. Detect line endings and normalize to LF for processing
            # We check if the original content used CRLF (\r\n)
            original_is_crlf = '\r\n' in content
            normalized_content = content.replace('\r\n', '\n')

            if not edits:
                return self.result("No edits provided.", False)

            # 3. Find all replacement points in the ORIGINAL normalized content
            # To ensure edits are matched against the original file (not incrementally),
            # we find all match offsets first.
            replacement_points = []
            for edit in edits:
                old_t = edit.get('old_text')
                new_t = edit.get('new_text')
                if not old_t or new_t is None:
                    continue

                start_idx = 0
                while True:
                    idx = normalized_content.find(old_t, start_idx)
                    if idx == -1:
                        break
                    replacement_points.append({
                        'start': idx,
                        'end': idx + len(old_t),
                        'new_text': new_t
                    })
                    start_idx = idx + len(old_t)

            # 4. Apply edits from back-to-front
            # Sorting by start index descending is the standard way to apply multiple
            # non-overlapping replacements in a single pass without invalidating
            # the indices of the remaining edits.
            replacement_points.sort(key=lambda x: x['start'], reverse=True)

            working_content = normalized_content
            for point in replacement_points:
                working_content = (
                    working_content[:point['start']] +
                    point['new_text'] +
                    working_content[point['end']:]
                )

            # 5. Restore original line endings (CRLF if necessary)
            if original_is_crlf:
                final_content = working_content.replace('\n', '\r\n')
            else:
                final_content = working_content

            # 6. Write the file back with the original BOM
            with open(file_path_str, 'wb') as f:
                f.write(bom)
                f.write(final_content.encode('utf-8'))

            # thanks gemma4 lol. this stuff is far beyond me

            return self.result(f"Successfully replaced {len(edits)} block(s) in {'.'.join(file_path)}.")

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def overwrite_file(self, project_name: str, file_path: list, content: str):
        """
        Writes to a file within a project.
        Overwrites the file with the content! Prefer using edit_file.

        Make sure to ALWAYS put a shebang at the top of a script! example: #!interpreter [arguments]

        Args:
            project_name: project name
            file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
            content: the new content of the file
        """
        file_path_str = self._get_file_path(project_name, file_path)

        try:
            with open(file_path_str, "w") as f:
                f.write(content)
            return self.result(True)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def search(self, project_name: str, file_path: list, query: str, context_lines: int = 5, max_matches: int = 10, use_regex: bool = False):
        """
        Search for a query within the file and return snippets with line numbers and context.
        Always use this before making any edits!

        Args:
            project_name: project name
            file_path: path to the file, as a list
            query: the search string or regex pattern
            context_lines: number of lines to show before and after each match
            max_matches: maximum number of matches to return
            use_regex: whether to treat the query as a regular expression
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            matches = []
            num_lines = len(lines)

            if use_regex:
                try:
                    pattern = re.compile(query, re.IGNORECASE)
                except re.error as e:
                    return self.result(f"Invalid regex pattern: {e}", False)
            else:
                query_lower = query.lower()

            for i, line in enumerate(lines):
                line_num = i + 1
                match_found = False
                
                if use_regex:
                    if pattern.search(line):
                        match_found = True
                else:
                    if query_lower in line.lower():
                        match_found = True
                
                if match_found:
                    snippet = [f"--- Match at line {line_num} ---"]
                    
                    # Determine window for context
                    start_idx = max(0, i - context_lines)
                    end_idx = min(num_lines, i + context_lines + 1)
                    
                    for j in range(start_idx, end_idx):
                        curr_line_num = j + 1
                        curr_line_content = lines[j].rstrip('\n\r')
                        
                        if curr_line_num == line_num:
                            snippet.append(f"{curr_line_num:4}: {curr_line_content}  <-- MATCH")
                        else:
                            snippet.append(f"{curr_line_num:4}: {curr_line_content}")
                    
                    matches.append("\n".join(snippet))
                    
                    if len(matches) >= max_matches:
                        break
            
            if not matches:
                return self.result(None)
            
            result_str = "\n\n".join(matches)
            return self.result(result_str)

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def execute(self, project_name: str, file_path: list, timeout: int = 30):
        """
        executes a file within a project. will automatically chmod for you if not done already

        Args:
            project_name: project name
            file_path: path to the file, as a list that will be joined by the OS's path separator using python os.path.join()
            timeout: maximum time in seconds to wait for execution
        """
        if not self.config.get("allow_code_execution"):
            return self.result("Code execution is disabled for security", False)

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        os.chmod(file_path_str, os.stat(file_path_str).st_mode | stat.S_IEXEC)
        try:
            proc = await asyncio.create_subprocess_exec(
                file_path_str,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                stdout_str = stdout.decode().strip()
                stderr_str = stderr.decode().strip()

                if proc.returncode != 0:
                    error_msg = stderr_str if stderr_str else f"Process exited with code {proc.returncode}"
                    return self.result(f"Error (exit code {proc.returncode}):\\n{error_msg}", False)
                
                return self.result(stdout_str)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except:
                    pass
                return self.result(f"Execution timed out after {timeout} seconds", False)
        except Exception as e:
            return self.result(f"error: {e}", False)
