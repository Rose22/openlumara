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
from typing import List, Dict, Any, Optional, Union

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    import tree_sitter_python as tspython
    HAS_TREE_SITTER = True
    # Pre-load the python language for efficiency
    PYTHON_LANGUAGE = tspython.language()
except ImportError:
    HAS_TREE_SITTER = False
    PYTHON_LANGUAGE = None

class Coder(modules.files_sandboxed.SandboxedFiles):
    """Allows your AI to write, edit and test code for you."""

    settings = {
        "coding_style": "Write clean, well-commented code. Do not include your reasoning inside final code.",
        "sandbox_folder": "~/coder",
        "read-only_mode": True,
        "allow_code_execution": False,
        "enable_progress_messages": False,
        "openlumara_module_creation_mode": False,
    }

    # Language heuristics for symbol searching and outline generation
    LANGUAGE_CONFIG = {
        'python': {
            'extensions': ['.py'],
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'body_type': 'indentation'
        },
        'javascript': {
            'extensions': ['.js', '.ts', '.jsx', '.tsx'],
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', 'variable'),
                (r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>', 'function'),
            ],
            'body_type': 'brace'
        },
        'cpp': {
            'extensions': ['.cpp', '.c', '.h', '.hpp', '.cc'],
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*struct\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'struct'),
                # Note: full function signatures in C++ are hard for regex, 
                # but we can catch many common patterns
                (r'^\s*[\w:<>\*]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', 'function'),
            ],
            'body_type': 'brace'
        },
        'go': {
            'extensions': ['.go'],
            'outline_patterns': [
                (r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+struct', 'struct'),
                (r'^\s*func\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'body_type': 'brace'
        },
        'java': {
            'extensions': ['.java'],
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:public|protected|private|static)\s+[\w<>[\]]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', 'function'),
            ],
            'body_type': 'brace'
        }
    }

    OPENLUMARA_MODULE_PROMPT = """
To create modules for OpenLumara, follow this spec:

```python
import core

class YourClassName(core.module.Module):
    \"\"\"You can put a description of your module here\"\"\"

    # contains settings definitions. these will show up in settings panels and can be changed by the user
    settings = {
        "key": "default_value",
        "save_data_path": "fancymoduledata"
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # dict that gets saved to persistent storage
        self.saved_dict = core.storage.StorageDict(self.config.get("save_data_path"), type="json") # available types: json, yaml, msgpack, markdown, text

        # list that gets saved to persistent storage
        self.saved_list = core.storage.StorageList(self.config.get("save_data_path"), type="json") # available types: json, yaml, msgpack, text

        self.whatever_variables_you_want = "whatever value you want"

    async def on_system_prompt(self):
        return "Return a string here, and it'll appear in your system prompt!"

    async def on_background(self):
        \"\"\"This will be automatically ran as an asyncio background task by the openlumara framework\"\"\"
        await self.channel.announce("This message pops up every minute. Very annoying!")
        await asyncio.sleep(60)

    async def my_function(self, name: str):
        \"\"\"A tool that can be called by AI. The docstring will show up in your tool description!\"\"\"
        # any code you want here
        name = name.lower()
        # use self.channel.announce to display notifications to the user! this can be during processing, or even in a background loop. this allows you to display messages without being prompted into it
        await self.channel.announce("wow! this message popped up all on its own!")

        try:
            ohnoididsomethingnaughty()
        except Exception as e:
            return self.result(f"error while trying to run my tool: {e}", success=False) # use success=False upon errors

        # you can even send a prompt to yourself and return the response!
        response_from_ai = self.channel.send_stream({"role": "user", "content": "how do you do, me?"})
        collected_tokens = []
        async for token in response_from_ai:
            # do whatever you want with the token. collect it, display it, whatever you want
            # tokens follow openAI's spec. they are a dict with two keys: type, and content.
            if token.get("type") == "content":
                collected_tokens.append(token.get("content"))
            elif token.get("type") == "reasoning":
                # do whatever with reasoning
                pass

        msg_from_ai = " ".join(collected_tokens)

        return self.result(f"this is my tool, {name}! also, {msg_from_ai}", success=True) # using self.result is VITAL to ensure the output of a tool gets properly returned and parsed

    @core.module.command("my_command", temporary=False, help={
        "": "show list of profiles", # this is shown for the command by itself without arguments
        "<name>": "show profile for <name>",
        "<name> <profile>": "set <name>'s profile to <profile>"
    })
    async def my_command(self, args: list):
        # arguments is 0-indexed. args[0] is the first argument, not the name of the command
        match len(args):
            case 0:
                return self.saved_dict.keys()
            case 1:
                return self.saved_dict.get(args[0], "profile not found")
            case 2:
                self.saved_dict[args[0]] = str(args[1])
                self.saved_dict.save()
                return "Profile stored!" # we don't use self.result() for user facing commands, only for AI-facing tools
            case _:
                return "invalid arguments"
"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.sandbox_path

    def _get_language_from_ext(self, file_path_str: str) -> str:
        ext = os.path.splitext(file_path_str)[1].lower()
        for lang, config in self.LANGUAGE_CONFIG.items():
            if ext in config['extensions']:
                return lang
        return 'generic'

    async def on_system_prompt(self):
        output = ""

        coding_style = self.config.get("coding_style")
        if coding_style:
            output += f"## Your coding style\nWhen coding, keep this coding style guide in mind:\n{coding_style}\n\n"

        if self.config.get("openlumara_module_creation_mode"):
            output += self.OPENLUMARA_MODULE_PROMPT.strip()
        else:
            file_list = os.listdir(self.sandbox_path)
            project_list = []
            for filename in file_list:
                if not os.path.isdir(os.path.join(self.sandbox_path, filename)):
                    continue

                project_list.append(filename)

            output += "## Current projects in sandbox\n"
            if not project_list:
                output += "No projects yet."

            try:
                output += "\n".join(project_list)
            except Exception as e:
                return f"error: {e}", False

        return output

    def _get_project_path(self, name: str):
        """returns the project path as a string within the sandbox"""
        return self._get_sandbox_path(name)

    def _get_file_path(self, project_name: str, file_path: list):
        """returns the path to a file in the project as a string within the sandbox"""
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
                            children.append(_build_tree(entry.path, current_depth + 1))
                except Exception:
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
            return self.result(os.listdir(target_path))
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def create_project(self, project_name: str, file_structure: dict):
        """
        Creates an entire project structure in one go!

        file_structure format:
        A dictionary where keys are directory names.
        - If a value is a dictionary, it represents a subdirectory.
        - If a value is a list, it represents a list of empty files to be created in that directory.

        Example:
        {
            "src": {
                "components": {
                    "button.py": {} # Wait, this creates a directory 'button.py'
                }
            },
            "tests": ["test_main.py", "test_utils.py"],
            "README.md": [] # This is not quite right for a single file
        }
        """
        if self.config.get("read-only_mode"):
            return self.result("User has disabled file modification. Provide the code directly to user.", False)

        async def _build_structure(current_path: str, structure: dict):
            for name, content in structure.items():
                if name == "root":
                    target_path = current_path
                else:
                    target_path = os.path.join(current_path, name)

                if isinstance(content, dict):
                    os.makedirs(target_path, exist_ok=True)
                    if self.config.get("enable_progress_messages"):
                        await self.manager.channel.announce(f"Created directory: {target_path}")
                    await _build_structure(target_path, content)
                elif isinstance(content, list):
                    os.makedirs(target_path, exist_ok=True)
                    for filename in content:
                        file_path = os.path.join(target_path, filename)
                        with open(file_path, "w") as f:
                            pass
                        if self.config.get("enable_progress_messages"):
                            await self.manager.channel.announce(f"Created file: {file_path}")

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
        Reads a file within a project.
        Prefer using get_outline() over read_file().
        This tool will flood your context with lots of tokens, so only use it as a last resort!
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        with open(file_path_str, "r") as f:
            result = f.read()

        return self.result(result)

    # async def edit_file(self, project_name: str, file_path: list, search: str, replace: str):
    #     """
    #     Edits a file within a project using search and replace.

    #     Each replacement is applied to the entire file content.
    #     """
    #     if self.config.get("read-only_mode"):
    #         return self.result("User has disabled file modification. Provide the code directly to user.", False)

    #     file_path_str = self._get_file_path(project_name, file_path)
    #     if not os.path.exists(file_path_str):
    #         return self.result("file does not exist!", False)

    #     try:
    #         with open(file_path_str, 'rb') as f:
    #             raw_bytes = f.read()

    #         bom = b''
    #         if raw_bytes.startswith(b'\xef\xbb\xbf'):
    #             bom = b'\xef\xbb\xbf'
    #             content = raw_bytes[len(bom):].decode('utf-8')
    #         else:
    #             content = raw_bytes.decode('utf-8')

    #         original_is_crlf = '\r\n' in content
    #         normalized_content = content.replace('\r\n', '\n')

    #         if not search or not replace:
    #             return self.result("You are missing one of search or replace..", False)

    #         replacement_points = []

    #         old_t = search
    #         new_t = replace

    #         start_idx = 0
    #         while True:
    #             idx = normalized_content.find(old_t, start_idx)
    #             if idx == -1:
    #                 break
    #             replacement_points.append({
    #                 'start': idx,
    #                 'end': idx + len(old_t),
    #                 'new_text': new_t
    #             })
    #             start_idx = idx + len(old_t)

    #         replacement_points.sort(key=lambda x: x['start'], reverse=True)

    #         working_content = normalized_content
    #         for point in replacement_points:
    #             working_content = (
    #                 working_content[:point['start']] +
    #                 point['new_text'] +
    #                 working_content[point['end']:]
    #             )

    #         if original_is_crlf:
    #             final_content = working_content.replace('\n', '\r\n')
    #         else:
    #             final_content = working_content

    #         with open(file_path_str, 'wb') as f:
    #             f.write(bom)
    #             f.write(final_content.encode('utf-8'))

    #         return self.result(f"Successfully replaced 1 block(s) in {'.'.join(file_path)}.")

    #     except Exception as e:
    #         return self.result(f"error: {e}", False)

    async def overwrite_file(self, project_name: str, file_path: list, content: str):
        """
        Writes to a file within a project.
        """
        if self.config.get("read-only_mode"):
            return self.result("User has disabled file modification. Provide the code directly to user.", False)

        file_path_str = self._get_file_path(project_name, file_path)

        try:
            with open(file_path_str, "w") as f:
                f.write(content)
            return self.result(True)
        except Exception as e:
            return self.result(f"error: {e}", False)

    # async def search(self, project_name: str, file_path: list, query: str, context_lines: int = 5, max_matches: int = 10, use_regex: bool = False):
    #     """
    #     Search for a query within the file and return snippets with line numbers and context.
    #     """
    #     file_path_str = self._get_file_path(project_name, file_path)
    #     if not os.path.exists(file_path_str):
    #         return self.result("file does not exist!", False)

    #     try:
    #         with open(file_path_str, 'r') as f:
    #             lines = f.readlines()

    #         matches = []
    #         num_lines = len(lines)

    #         if use_regex:
    #             try:
    #                 pattern = re.compile(query, re.IGNORECASE)
    #             except re.error as e:
    #                 return self.result(f"Invalid regex pattern: {e}", False)
    #         else:
    #             query_lower = query.lower()

    #         for i, line in enumerate(lines):
    #             line_num = i + 1
    #             match_found = False
                
    #             if use_regex:
    #                 if pattern.search(line):
    #                     match_found = True
    #             else:
    #                 if query_lower in line.lower():
    #                     match_found = True
                
    #             if match_found:
    #                 snippet = [f"--- Match at line {line_num} ---"]
                    
    #                 start_idx = max(0, i - context_lines)
    #                 end_idx = min(num_lines, i + context_lines + 1)
                    
    #                 for j in range(start_idx, end_idx):
    #                     curr_line_num = j + 1
    #                     curr_line_content = lines[j].rstrip('\n\r')
                        
    #                     if curr_line_num == line_num:
    #                         snippet.append(f"{curr_line_num:4}: {curr_line_content}  <-- MATCH")
    #                     else:
    #                         snippet.append(f"{curr_line_num:4}: {curr_line_content}")
                    
    #                 matches.append("\n".join(snippet))
                    
    #                 if len(matches) >= max_matches:
    #                     break
            
    #         if not matches:
    #             return self.result(None)
            
    #         result_str = "\n\n".join(matches)
    #         return self.result(result_str)

    #     except Exception as e:
    #         return self.result(f"error: {e}", False)

    async def execute(self, project_name: str, file_path: list, timeout: int = 30):
        """
        executes a file within a project.
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
                    return self.result(f"Error (exit code {proc.returncode}):\n{error_msg}", False)
                
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

    async def get_outline(self, project_name: str, file_path: list, language: str = None) -> List[Dict[str, Any]]:
        """
        Returns a list of symbols (classes, functions, etc.) with their names, types, and line numbers.
        The language can be specified, or it will be guessed from the extension.

        ALWAYS use this to read code! Only ever use read_file if get_outline didn't provide enough information.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        config = self.LANGUAGE_CONFIG.get(language)
        
        # If we don't have specific patterns, use a very generic fallback
        if not config:
            patterns = [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ]
        else:
            patterns = config['outline_patterns']

        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            outline = []
            for idx, line in enumerate(lines):
                for pattern, sym_type in patterns:
                    match = re.search(pattern, line)
                    if match:
                        outline.append({
                            "name": match.group(1),
                            "type": sym_type,
                            "line": idx + 1
                        })
                        break
            
            return self.result(outline)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def get_symbol_body(self, project_name: str, file_path: list, line_number: int, language: str = None) -> str:
        """
        Returns the actual block of code for a symbol starting at the given line number.
        Uses indentation-based logic for Python and brace-counting for C-style languages.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)
        
        config = self.LANGUAGE_CONFIG.get(language)
        body_type = config['body_type'] if config else 'brace'

        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("line number out of range", False)

            start_idx = line_number - 1
            
            if body_type == 'indentation':
                # Python indentation-based logic
                def get_indent(l):
                    return len(l) - len(l.lstrip())
                
                base_indent = get_indent(lines[start_idx])
                end_idx = start_idx + 1
                
                for i in range(start_idx + 1, len(lines)):
                    line = lines[i]
                    stripped = line.strip()
                    if not stripped or stripped.startswith('#'):
                        continue
                    if get_indent(line) <= base_indent:
                        break
                    end_idx = i + 1
                
                body_lines = lines[start_idx:end_idx]
            
            else:
                # Brace-based logic (JS, C++, Java, etc.)
                # 1. Find the first '{' after or at the start line
                brace_found = False
                start_brace_idx = -1
                
                for i in range(start_idx, len(lines)):
                    if '{' in lines[i]:
                        start_brace_idx = i
                        brace_found = True
                        break
                
                if not brace_found:
                    # If no brace found (e.g. single line function), return just that line
                    return self.result("".join(lines[start_idx:start_idx+1]))

                # 2. Count braces
                brace_count = 0
                end_idx = len(lines)
                for i in range(start_brace_idx, len(lines)):
                    line = lines[i]
                    # Very simple brace counting (ignores braces in strings/comments)
                    brace_count += line.count('{')
                    brace_count -= line.count('}')
                    
                    if brace_count <= 0:
                        end_idx = i + 1
                        break
                
                body_lines = lines[start_idx:end_idx]

            return self.result("".join(body_lines))
        except Exception as e:
            return self.result(f"error: {e}", False)
