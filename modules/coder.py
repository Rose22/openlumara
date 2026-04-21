import core
import os
import sys
import re
import subprocess
import stat
import shutil
import itertools
import asyncio
import importlib
import modules.files_sandboxed
from typing import List, Dict, Any, Optional, Union

# --- Improved Tree-sitter Setup ---
HAS_TREE_SITTER = False
LANGUAGE_MAP = {}

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True

    def _try_import_lang(mod_name, lang_key):
        """Attempts to import a language parser and add it to the map."""
        try:
            mod = importlib.import_module(mod_name)
            # tree-sitter 0.22+ returns a PyCapsule from .language()
            # We MUST wrap it in Language() to create the expected object
            LANGUAGE_MAP[lang_key] = Language(mod.language())
            return True
        except (ImportError, AttributeError):
            return False

    # Define the list of parsers we want to attempt to load
    languages_to_attempt = [
        ('tree_sitter_python', 'python'),
        ('tree_sitter_javascript', 'javascript'),
        ('tree_sitter_typescript', 'typescript'),
        ('tree_sitter_html', 'html'),
        ('tree_sitter_css', 'css'),
        ('tree_sitter_cpp', 'cpp'),
        ('tree_sitter_c_sharp', 'c-sharp'),
        ('tree_sitter_rust', 'rust'),
        ('tree_sitter_ruby', 'ruby'),
        ('tree_sitter_go', 'go'),
        ('tree_sitter_java', 'java'),
    ]

    loaded_languages = []
    for mod_name, lang_key in languages_to_attempt:
        if _try_import_lang(mod_name, lang_key):
            loaded_languages.append(lang_key)

    # Report status based on what was actually loaded
    if not loaded_languages:
        core.log("coder", "Tree-sitter is installed, but NO language parsers (e.g., tree_sitter_python) were detected.")
    else:
        core.log("coder", f"Tree-sitter is ENABLED. Loaded languages: {loaded_languages}")

except ImportError as e:
    HAS_TREE_SITTER = False
    core.log("coder", f"Tree-sitter is NOT enabled. Reason: The 'tree_sitter' core library is missing. ({e})")
except Exception as e:
    HAS_TREE_SITTER = False
    core.log("coder", f"Tree-sitter setup encountered an unexpected error: {e}")

class Coder(modules.files_sandboxed.SandboxedFiles):
    """Allows your AI to write, edit and test code for you."""

    settings = {
        "coding_style": "Write clean, well-commented code. Do not include your reasoning inside final code.",
        "sandbox_folder": "~/coder",
        "read-only": True,
        "allow_function_editing": False,
        "allow_full_file_reads": False,
        "allow_full_file_overwrites": False,
        "allow_code_execution": False,
        "enable_progress_messages": False,
        "openlumara_module_creation_mode": False,
    }

    # Language heuristics for symbol searching and outline generation
    LANGUAGE_REGEXES = {
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
                (r'^\s*[\w:<>*]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', 'function'),
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
                (r'^\s*(?:public|protected|private|static)\s+[\w<>\[\]]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', 'function'),
            ],

            'body_type': 'brace'
        }
    }

    # Mapping extensions to language keys
    LANGUAGE_CONFIG = {
        'python': {'extensions': ['.py']},
        'javascript': {'extensions': ['.js', '.ts', '.jsx', '.tsx']},
        'typescript': {'extensions': ['.ts', '.tsx']},
        'html': {'extensions': ['.html']},
        'css': {'extensions': ['.css']},
        'cpp': {'extensions': ['.cpp', '.c', '.h', '.hpp', '.cc']},
        'c-sharp': {'extensions': ['.cs']},
        'rust': {'extensions': ['.rs']},
        'ruby': {'extensions': ['.rb']},
        'go': {'extensions': ['.go']},
        'java': {'extensions': ['.java']}
    }

    # AST Node Type -> Symbol Type mapping
    SYMBOL_MAP = {
        'python': {
            'class_definition': 'class',
            'function_definition': 'function'
        },
        'javascript': {
            'class_declaration': 'class',
            'function_declaration': 'function',
            'method_definition': 'method',
            'arrow_function': 'function'
        },
        'typescript': {
            'class_declaration': 'class',
            'function_declaration': 'function',
            'method_definition': 'method'
        },
        'cpp': {
            'class_specifier': 'class',
            'struct_specifier': 'struct',
            'function_definition': 'function',
            'method_definition': 'method'
        },
        'go': {
            'type_declaration': 'struct',
            'function_declaration': 'function',
            'method_declaration': 'method'
        },
        'java': {
            'class_declaration': 'class',
            'method_declaration': 'method',
            'constructor_declaration': 'method'
        },
        'rust': {
            'struct_item': 'struct',
            'enum_item': 'enum',
            'fn': 'function',
            'impl_item': 'impl'
        },
        'ruby': {
            'class': 'class',
            'module': 'module',
            'def': 'function'
        },
        'c-sharp': {
            'class_declaration': 'class',
            'method_declaration': 'method'
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
        # arguments is 0-indexed. args[0] is not the name of the command, but the first argument
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

        # disable any tools that were disabled via config
        if self.config.get("read-only"):
            self.disabled_tools.append("create_project")

        if not self.config.get("allow_function_editing") or self.config.get("read-only"):
            self.disabled_tools.append("edit_symbol_content")

        if not self.config.get("allow_full_file_reads") or self.config.get("read-only"):
            self.disabled_tools.append("read_file")

        if not self.config.get("allow_full_file_overwrites") or self.config.get("read-only"):
            self.disabled_tools.append("overwrite_file")

        if not self.config.get("allow_code_execution"):
            self.disabled_tools.append("execute")

        # disable search if treesitter is available
        if HAS_TREE_SITTER:
            self.disabled_tools.append("search")

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
            output += f"## Your coding style\\nWhen coding, keep this coding style guide in mind:\\n{coding_style}\\n\\n"

        if self.config.get("openlumara_module_creation_mode"):
            output += self.OPENLUMARA_MODULE_PROMPT.strip()
        else:
            file_list = os.listdir(self.sandbox_path)
            project_list = []
            for filename in file_list:
                if not os.path.isdir(os.path.join(self.sandbox_path, filename)):
                    continue

                project_list.append(filename)

            output += "## Current projects in sandbox\\n"
            if not project_list:
                output += "No projects yet."

            try:
                output += "\\n".join(project_list)
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

    async def list_full_project_tree(self, project_name: str, depth_limit: int = 3):
        """
        Returns a recursive tree representation of the project structure.
        Structure:
        {
           "root": ["file1.py", "file2.md"],
           "subfolder": ["file1.txt", "file2.txt", {"another_subfolder": ["subfile1.txt", "subfile2.txt"]}]
        }
        """
        project_path = self._get_project_path(project_name)
        if not os.path.exists(project_path):
            return self.result("project does not exist", False)

        def _build_tree(path, current_depth):
            is_dir = os.path.isdir(path)
            if not is_dir:
                return os.path.basename(path)

            contents = []
            subdirs = {}
            try:
                for entry in os.scandir(path):
                    if entry.is_file():
                        contents.append(entry.name)
                    elif entry.is_dir():
                        if current_depth < depth_limit:
                            subdirs[entry.name] = _build_tree(entry.path, current_depth + 1)
                        else:
                            contents.append(entry.name)
            except Exception:
                pass

            if current_depth > 0:
                return contents + list(subdirs.values())
            else:
                result = {"root": contents}
                result.update(subdirs)
                return result

        try:
            tree = _build_tree(project_path, 0)
            return self.result(tree)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def list_project_folder(self, project_name: str, sub_path: list = None):
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
                    "button.py": "#!/bin/env python3\\nhi this is some example code!"
                }
            },
            "tests": ["test_main.py", "test_utils.py"],
            "README.md": "this is a readme"
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
                            if content:
                                f.write(content)
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

    async def get_outline(self, project_name: str, file_path: list, language: str = None) -> List[Dict[str, Any]]:
        """
        Returns a list of symbols (classes, functions, etc.) using Tree-sitter if available,
        otherwise falling back to regex.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                symbols = []
                self._walk_for_symbols(tree.root_node, language, symbols)
                symbols.sort(key=lambda x: x['line'])

                # Return only name and type as requested
                return self.result([{"name": s["name"], "type": s["type"]} for s in symbols])
            except Exception as e:
                core.log("coder", f"Couldn't use tree-sitter! Falling back to regex: {e}")
                pass # Fallback to regex

        # 2. Fallback to Regex
        patterns = []
        config = self.LANGUAGE_CONFIG.get(language)
        if config and 'outline_patterns' in config:
            patterns = config['outline_patterns']
        else:
            # Generic fallback patterns
            patterns = [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ]

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
                            "type": sym_type
                        })
                        break
            return self.result(outline)
        except Exception as e:
            return self.result(f"error: {e}", False)

    def _walk_for_symbols(self, node, language, symbols, prefix=""):
        """Recursive tree walker for Tree-sitter nodes."""
        target_types = self.SYMBOL_MAP.get(language, {})

        if node.type in target_types:
            sym_type = target_types[node.type]
            name = None

            # Search children for the identifier/name of the symbol
            for child in node.children:
                if child.type in ['identifier', 'property_identifier', 'name', 'field_identifier']:
                    try:
                        name = child.text.decode('utf-8')
                        break
                    except:
                        continue

            if name:
                full_name = f"{prefix}{name}"
                symbols.append({
                    'name': full_name,
                    'type': sym_type,
                    'line': node.start_point[0] + 1
                })
                # For children, use this symbol's name as prefix
                for child in node.children:
                    self._walk_for_symbols(child, language, symbols, prefix=f"{full_name}.")
                return # We've already explored descendants with the prefix

        for child in node.children:
            self._walk_for_symbols(child, language, symbols, prefix=prefix)

    def _find_symbol_line(self, file_path_str: str, symbol_name: str, language: str) -> int:
        """Helper to find the line number of a symbol by its name."""
        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()
                tree = parser.parse(source_bytes)

                target_node = None
                parts = symbol_name.split('.')

                def find_node(node, parts_to_match):
                    nonlocal target_node
                    if target_node or not parts_to_match:
                        return

                    current_part = parts_to_match[0]
                    remaining_parts = parts_to_match[1:]

                    # Check if this node is a symbol and matches current_part
                    if node.type in self.SYMBOL_MAP.get(language, {}):
                        for child in node.children:
                            if child.type in ['identifier', 'property_identifier', 'name', 'field_identifier']:
                                try:
                                    if child.text.decode('utf-8') == current_part:
                                        if not remaining_parts:
                                            target_node = node
                                            return
                                        else:
                                            # Search within this node for the rest of the parts
                                            for next_child in node.children:
                                                find_node(next_child, remaining_parts)
                                            return
                                except:
                                    continue

                    # Search children for the current part
                    for child in node.children:
                        find_node(child, parts_to_match)

                find_node(tree.root_node, parts)
                if target_node:
                    return target_node.start_point[0] + 1
            except Exception:
                pass

        # 2. Fallback to Regex
        parts = symbol_name.split('.')
        last_part = parts[-1]
        config = self.LANGUAGE_CONFIG.get(language)
        patterns = []
        if config and 'outline_patterns' in config:
            patterns = config['outline_patterns']
        else:
            # Generic fallback patterns
            patterns = [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ]

        try:
            with open(file_path_str, 'r') as f:
                for idx, line in enumerate(f):
                    for pattern, sym_type in patterns:
                        match = re.search(pattern, line)
                        if match and match.group(1) == last_part:
                            return idx + 1
        except Exception:
            pass

        return None

    async def get_symbol_body(self, project_name: str, file_path: list, symbol_name: str, language: str = None) -> str:
        """
        Returns the code block for a symbol.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"symbol '{symbol_name}' not found", False)

        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                from tree_sitter import Parser
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                # Strategy: Find the smallest node that covers this specific line
                # that is also recognized as a symbol.
                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        node_type = node.type
                        if node_type in self.SYMBOL_MAP.get(language, {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    # Pick the "tightest" node (the one with the smallest byte range)
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    return self.result(source_bytes[best_node.start_byte:best_node.end_byte].decode('utf-8'))
                else:
                    core.log("coder", "[DEBUG] Tree-sitter found 0 matching symbols for this line. Falling back.")
            except Exception as e:
                core.log("coder", f"Couldn't use tree-sitter! Falling back to regex: {e}")
                pass # Fallback to regex
        elif language not in LANGUAGE_MAP:
            core.log("coder", f"Couldn't use tree-sitter! Language '{language}' not supported.")

        # 2. Fallback to original Indentation/Brace logic
        config = self.LANGUAGE_CONFIG.get(language)
        body_type = config.get('body_type', 'brace') if config else 'brace'

        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("line number out of range", False)

            start_idx = line_number - 1

            if body_type == 'indentation':
                def get_indent(l): return len(l) - len(l.lstrip())
                base_indent = get_indent(lines[start_idx])
                end_idx = start_idx + 1
                for i in range(start_idx + 1, len(lines)):
                    line = lines[i]
                    if not line.strip() or line.strip().startswith('#'): continue
                    if get_indent(line) <= base_indent: break
                    end_idx = i + 1
                body_lines = lines[start_idx:end_idx]
            else:
                # Brace-based logic
                brace_found = False
                start_brace_idx = -1
                for i in range(start_idx, len(lines)):
                    if '{' in lines[i]:
                        start_brace_idx = i
                        brace_found = True
                        break
                if not brace_found:
                    return self.result("".join(lines[start_idx:start_idx+1]))

                brace_count = 0
                end_idx = len(lines)
                for i in range(start_brace_idx, len(lines)):
                    line = lines[i]
                    brace_count += line.count('{')
                    brace_count -= line.count('}')
                    if brace_count <= 0:
                        end_idx = i + 1
                        break
                body_lines = lines[start_idx:end_idx]

            return self.result("".join(body_lines))
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def edit_symbol_body(self, project_name: str, file_path: list, symbol_name: str, new_content: str, language: str = None) -> bool:
        """
        Replaces the content of a symbol with new content.
        Uses the same logic as get_symbol_body to identify the symbol's boundaries.

        Args:
            project_name: Name of the project.
            file_path: List representing the path to the file.
            symbol_name: Name of the symbol.
            new_content: The new string content to place in the symbol.
            language: Optional language identifier.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return False

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return False

        # remove any extra whitespace
        new_content = new_content.strip()

        # 1. Try Tree-sitter for precise byte-level replacement
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                from tree_sitter import Parser
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        if node.type in self.SYMBOL_MAP.get(language, {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    # Pick the \"tightest\" node (the one with the smallest byte range)
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    start_byte = best_node.start_byte
                    end_byte = best_node.end_byte

                    # Perform the replacement in bytes to preserve exact encoding/spacing
                    new_content_bytes = new_content.encode('utf-8')
                    updated_bytes = source_bytes[:start_byte] + new_content_bytes + source_bytes[end_byte:]

                    with open(file_path_str, 'wb') as f:
                        f.write(updated_bytes)
                    return True
            except Exception as e:
                core.log("coder", f"Couldn't use tree-sitter: {e}")
                pass

        # 2. Fallback to line-based replacement matching get_symbol_body's logic
        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return False

            config = self.LANGUAGE_CONFIG.get(language)
            body_type = config.get('body_type', 'brace') if config else 'brace'

            start_idx = line_number - 1
            end_idx = -1

            if body_type == 'indentation':
                def get_indent(l): return len(l) - len(l.lstrip())
                base_indent = get_indent(lines[start_idx])
                end_idx = start_idx + 1
                for i in range(start_idx + 1, len(lines)):
                    line = lines[i]
                    if not line.strip() or line.strip().startswith('#'):
                        continue
                    if get_indent(line) <= base_indent:
                        break
                    end_idx = i + 1
            else:
                # Brace-based logic
                brace_found = False
                start_brace_idx = -1
                for i in range(start_idx, len(lines)):
                    if '{' in lines[i]:
                        start_brace_idx = i
                        brace_found = True
                        break

                if not brace_found:
                    end_idx = start_idx + 1
                else:
                    brace_count = 0
                    end_idx = len(lines)
                    for i in range(start_brace_idx, len(lines)):
                        line = lines[i]
                        brace_count += line.count('{')
                        brace_count -= line.count('}')
                        if brace_count <= 0:
                            end_idx = i + 1
                            break

            # Final safety check for end_idx
            if end_idx == -1:
                end_idx = start_idx + 1

            # Split new content into lines, preserving line endings
            new_lines = new_content.splitlines(keepends=True)
            if not new_lines:
                new_lines = [""]

            # Replace the identified slice of lines with the new content
            lines[start_idx:end_idx] = new_lines

            with open(file_path_str, 'w') as f:
                f.writelines(lines)
            return True

        except Exception as e:
            core.log("coder", f"Couldn't use tree-sitter: {e}")
            return False

    async def add_symbol_before(self, project_name: str, file_path: list, target_symbol_name: str, name: str, content_body: str, language: str = None) -> bool:
        """
        Inserts a new symbol (function or method) before the target symbol.

        Args:
            project_name: Name of the project.
            file_path: List representing the path to the file.
            target_symbol_name: The name of the symbol to insert before.
            name: The name of the new symbol.
            content_body: The content of the new symbol. If it doesn't contain a definition, one will be constructed.
            language: Optional language identifier.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return False

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # 1. Find the line number of the target symbol
        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return False

        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            # 2. Determine indentation of the target symbol to match it
            target_line = lines[line_number - 1]
            indent_len = len(target_line) - len(target_line.lstrip())
            indent_str = " " * indent_len

            # 3. Construct the new symbol content
            stripped_body = content_body.strip()
            is_method = "." in target_symbol_name

            # Check if content_body is just a body or a full definition
            if not stripped_body.startswith(('def ', 'class ', 'async def ')):
                # It's a body; construct the definition line
                if is_method:
                    new_symbol = f"{indent_str}def {name}(self):\n"
                else:
                    new_symbol = f"{indent_str}def {name}():\n"

                # If the body itself isn't indented, indent it to match
                if stripped_body and not content_body.startswith((' ', '\t')):
                    body_lines = content_body.splitlines(keepends=True)
                    indented_body = "".join([f"{indent_str}{line}" for line in body_lines])
                    new_symbol += indented_body
                else:
                    new_symbol += content_body
            else:
                # It's already a full definition.
                # If it's a method, we must ensure the whole definition is indented.
                if is_method:
                    body_lines = content_body.splitlines(keepends=True)
                    new_symbol = "".join([f"{indent_str}{line}" for line in body_lines])
                else:
                    new_symbol = content_body

            # Ensure the new symbol ends with a newline for clean insertion
            if not new_symbol.endswith('\n'):
                new_symbol += '\n'
            new_symbol += \n # and an extra one for better separation

            # 4. Insert the new symbol into the lines list before the target line
            lines.insert(line_number - 1, new_symbol)

            with open(file_path_str, 'w') as f:
                f.writelines(lines)
            return True

        except Exception as e:
            # Assuming 'core' is available in the namespace as seen in other methods
            try:
                import core
                core.log("coder", f"Error in add_symbol_before: {e}")
            except:
                print(f"Error in add_symbol_before: {e}")
            return False


    async def delete_symbol(self, project_name: str, file_path: list, symbol_name: str, language: str = None) -> bool:
        """
        Deletes a symbol from a file.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return False

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return False

        # 1. Try Tree-sitter for precise byte-level removal
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                from tree_sitter import Parser
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        if node.type in self.SYMBOL_MAP.get(language, {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    start_byte = best_node.start_byte
                    end_byte = best_node.end_byte

                    updated_bytes = source_bytes[:start_byte] + source_bytes[end_byte:]

                    with open(file_path_str, 'wb') as f:
                        f.write(updated_bytes)
                    return True
            except Exception as e:
                try:
                    import core
                    core.log("coder", f"Couldn't use tree-sitter for delete: {e}")
                except:
                    pass

        # 2. Fallback to line-based removal
        try:
            with open(file_path_str, 'r') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return False

            config = self.LANGUAGE_CONFIG.get(language)
            body_type = config.get('body_type', 'brace') if config else 'brace'

            start_idx = line_number - 1
            end_idx = -1

            if body_type == 'indentation':
                def get_indent(l): return len(l) - len(l.lstrip())
                base_indent = get_indent(lines[start_idx])
                end_idx = start_idx + 1
                for i in range(start_idx + 1, len(lines)):
                    line = lines[i]
                    if not line.strip() or line.strip().startswith('#'):
                        continue
                    if get_indent(line) <= base_indent:
                        break
                    end_idx = i + 1
            else:
                # Brace-based logic
                brace_found = False
                start_brace_idx = -1
                for i in range(start_idx, len(lines)):
                    if '{' in lines[i]:
                        start_brace_idx = i
                        brace_found = True
                        break

                if not brace_found:
                    end_idx = start_idx + 1
                else:
                    brace_count = 0
                    end_idx = len(lines)
                    for i in range(start_brace_idx, len(lines)):
                        line = lines[i]
                        brace_count += line.count('{')
                        brace_count -= line.count('}')
                        if brace_count <= 0:
                            end_idx = i + 1
                            break

            if end_idx == -1:
                end_idx = start_idx + 1

            del lines[start_idx:end_idx]

            with open(file_path_str, 'w') as f:
                f.writelines(lines)
            return True

        except Exception as e:
            try:
                import core
                core.log("coder", f"Error in delete_symbol: {e}")
            except:
                pass
            return False

    async def search(self, project_name: str, file_path: list, query: str, context_lines: int = 5, max_matches: int = 10, use_regex: bool = False):
        """
        Search for a query within the file and return snippets with line numbers and context.
        """
        # only use this when treesitter is not available, since searching manually is inferior

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

                    start_idx = max(0, i - context_lines)
                    end_idx = min(num_lines, i + context_lines + 1)

                    for j in range(start_idx, end_idx):
                        curr_line_num = j + 1
                        curr_line_content = lines[j].rstrip('\\n\\r')

                        if curr_line_num == line_num:
                            snippet.append(f"{curr_line_num:4}: {curr_line_content}  <-- MATCH")
                        else:
                            snippet.append(f"{curr_line_num:4}: {curr_line_content}")

                    matches.append("\\n".join(snippet))

                    if len(matches) >= max_matches:
                        break

            if not matches:
                return self.result(None)

            result_str = "\\n\\n".join(matches)
            return self.result(result_str)

        except Exception as e:
            return self.result(f"error: {e}", False)
