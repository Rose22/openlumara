import core
import os
import asyncio
import importlib
import glob as glob_module
import regex
import time
import shutil
import stat
from typing import Dict, Any, Optional, Tuple

# Tree-sitter Setup (Always available via dependencies)
LANGUAGE_MAP = {}
loaded_languages = []

import tree_sitter
from tree_sitter import Language, Parser

class Coder(core.module.Module):
    """Allows your AI to write, edit and test code."""

    dependencies = [
        "regex", "tree-sitter", "tree-sitter-python", "tree-sitter-javascript",
        "tree-sitter-cpp", "tree-sitter-c-sharp",
        "tree-sitter-rust", "tree-sitter-ruby", "tree-sitter-go", "tree-sitter-java"
    ]

    FORMATTERS = {
        'python': ['black', 'autopep8', 'yapf'],
        'javascript': ['prettier', 'eslint'],
        'typescript': ['prettier', 'eslint'],
        'ruby': ['rubocop', 'rufo'],
        'go': ['gofmt', 'goimports'],
        'rust': ['rustfmt'],
        'java': ['google-java-format'],
        'c-sharp': ['csharpier'],
        'cpp': ['clang-format'],
    }

    LANGUAGES = {
        'python': {
            'extensions': ['.py'], 'body_type': 'indentation',
            'symbol_types': {'class_definition': 'class', 'function_definition': 'function'}
        },
        'javascript': {
            'extensions': ['.js', '.jsx'], 'body_type': 'brace',
            'symbol_types': {'class_declaration': 'class', 'function_declaration': 'function', 'method_definition': 'method', 'arrow_function': 'function'}
        },
        'cpp': {
            'extensions': ['.cpp', '.c', '.h', '.hpp', '.cc'], 'body_type': 'brace',
            'symbol_types': {'class_specifier': 'class', 'struct_specifier': 'struct', 'function_definition': 'function'}
        },
        'c-sharp': {
            'extensions': ['.cs'], 'body_type': 'brace',
            'symbol_types': {'class_declaration': 'class', 'method_declaration': 'method'}
        },
        'rust': {
            'extensions': ['.rs'], 'body_type': 'brace',
            'symbol_types': {'struct_item': 'struct', 'enum_item': 'enum', 'fn': 'function', 'impl_item': 'impl'}
        },
        'ruby': {
            'extensions': ['.rb'], 'body_type': 'indentation',
            'symbol_types': {'class': 'class', 'module': 'module', 'def': 'function'}
        },
        'go': {
            'extensions': ['.go'], 'body_type': 'brace',
            'symbol_types': {'type_declaration': 'struct', 'function_declaration': 'function', 'method_declaration': 'method'}
        },
        'java': {
            'extensions': ['.java'], 'body_type': 'brace',
            'symbol_types': {'class_declaration': 'class', 'method_declaration': 'method', 'constructor_declaration': 'method'}
        }
    }

    settings = {
        "sandbox_folder": {"default": "~/coder", "description": "The path to the folder where all your projects are stored. The AI can only access files within this sandbox."},
        "template_folder": {
            "default": "modules/coder/templates",
            "description": "The path to the folder with all your code templates. This can be used by the AI to, for example, create an openlumara module from scratch very easily, then modify it to suit your needs."
        },
        "reading_mode": {"default": "symbols", "type": "select", "options": {"none": "Prevent reading any files", "symbols": "Target specific symbols for reading", "files": "Read entire files with limits", "both": "Enable both symbol and file reading"}},
        "writing_mode": {"default": "symbols", "type": "select", "options": {"read-only": "Prevent writing", "symbols": "Edit via symbols", "full edits": "Direct file edits", "both": "Enable both modes"}},
        "allow_total_overwrites": {"description": "Allow full file overwrites in full edits mode. Dangerous with some models.", "default": False},
        "coding_style": {"default": "", "description": "Style guidelines added to the system prompt.", "type": "long_text"},
        "add_project_list_to_system_prompt": {"default": True, "description": "Add available projects to the system prompt."},
        "limits": {
            "folder_blacklist": {"description": "Folders to skip during recursive listing.", "default": ["venv", "__pycache__"]},
            "max_file_size": {"description": "Max file size in MB for reading.", "default": 10},
            "max_read_lines": {"description": "Max lines to read per file.", "default": 1000},
            "max_grep_results": 50,
            "backup_retention_count": {"description": "Backups to keep per file.", "default": 10}
        },
        "allow_code_execution": {"description": "Execute written code. Extremely dangerous.", "unsafe": True, "default": False}
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # --- Dynamic Tree-sitter Loading ---
        for dep in self.dependencies:
            if dep.startswith("tree-sitter-"):
                # Convert package name (hyphens) to module name (underscores)
                module_name = dep.replace("-", "_")
                lang_key = dep[len("tree-sitter-"):]
                try:
                    mod = importlib.import_module(module_name)
                    LANGUAGE_MAP[lang_key] = Language(mod.language())
                except (ImportError, AttributeError, Exception) as e:
                    self.log("coder", f"Failed to load tree-sitter language '{lang_key}': {e}")

    async def on_ready(self):
        self._parser_cache = {}
        self.enabled_tools = []
        self.sandbox_path = os.path.expanduser(str(self.config.get("sandbox_folder", default="~/sandbox"))).rstrip(os.path.sep)
        self.templates_path = os.path.abspath(core.get_path(self.config.get("template_folder")))

        # prevents ReDoS attacks on every part of the coder that uses regexes
        # by using the regex library instead of standard 're'
        self.regex_timeout = 5.0

        self.enabled_tools.extend(["list_project_folders", "list_project_subfolder", "get_template"])

        symbol_reading_tools = ["get_outline", "get_symbol", "format_file"]
        symbol_writing_tools = ["create_project", "create_file", "edit_symbol", "add_symbol_before", "add_symbol_after", "delete_symbol"]
        file_reading_tools = ["read_file", "search", "grep", "find_files", "format_file"]
        file_writing_tools = ["create_project", "create_file", "append_to_file", "edit", "replace", "format_file"]

        match self.config.get("reading_mode"):
            case "symbols": self.enabled_tools.extend(symbol_reading_tools)
            case "files": self.enabled_tools.extend(file_reading_tools)
            case "both": self.enabled_tools.extend(symbol_reading_tools + file_reading_tools)

        if self.config.get("writing_mode") != "read-only":
            self.enabled_tools.extend(["list_backups", "restore_backup"])

        match self.config.get("writing_mode"):
            case "symbols": self.enabled_tools.extend(symbol_writing_tools)
            case "full edits": self.enabled_tools.extend(file_writing_tools)
            case "both": self.enabled_tools.extend(symbol_writing_tools + file_writing_tools)

        if self.config.get("writing_mode") in ("full edits", "both") and self.config.get("allow_total_overwrites"):
            self.enabled_tools.append("overwrite_file")

        if self.config.get("allow_code_execution"):
            self.enabled_tools.append("execute")

        for prop_name in dir(self):
            if prop_name.startswith("_") or prop_name.startswith("on_"):
                continue
            attr = getattr(self, prop_name)
            if callable(attr) and prop_name not in self.enabled_tools:
                self.disabled_tools.append(prop_name)

    def _get_project_path(self, project_name: str) -> str:
        return core.sandbox_path(self.sandbox_path, project_name.strip(os.path.sep))

    def _get_file_path(self, project_name: str, file_path: str) -> str:
        combined = os.path.join(project_name, file_path.strip(os.path.sep))
        return core.sandbox_path(self.sandbox_path, combined)

    def _check_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        max_size_bytes = self.config.get("limits", {}).get("max_file_size", 10) * 1024 * 1024
        try:
            size = os.path.getsize(file_path)
            if size > max_size_bytes:
                return False, f"File size ({size / (1024*1024):.1f}MB) exceeds limit ({max_size_bytes // (1024*1024)}MB)"
            return True, None
        except OSError:
            return True, None

    def _get_parser(self, language: str):
        if language not in self._parser_cache:
            self._parser_cache[language] = Parser(LANGUAGE_MAP[language])
        return self._parser_cache.get(language)

    def _parse_file(self, file_path: str, language: str) -> Optional[Tuple[Any, bytes]]:
        parser = self._get_parser(language)
        if not parser:
            return None
        try:
            with open(file_path, 'rb') as f:
                source_bytes = f.read()
            return parser.parse(source_bytes), source_bytes
        except Exception as e:
            self.log("coder", f"Parse failed: {e}")
            return None

    def _verify_syntax(self, file_path: str) -> Tuple[bool, Optional[str]]:
        lang = self._get_language_from_ext(file_path)
        if lang not in LANGUAGE_MAP:
            return True, None
        result = self._parse_file(file_path, lang)
        if not result:
            return True, None
        tree, source_bytes = result
        if not tree.root_node.has_error:
            return True, None

        error_node = None
        def find_error(n):
            nonlocal error_node
            if n.type in ('ERROR', 'MISSING'):
                error_node = n
                return
            if not error_node:
                for child in n.children:
                    find_error(child)
        find_error(tree.root_node)

        if error_node:
            line = error_node.start_point[0] + 1
            col = error_node.start_point[1] + 1
            snippet = source_bytes[error_node.start_byte:error_node.end_byte].decode('utf-8', errors='replace').strip()
            return False, f"Syntax error at line {line}, column {col}: {snippet!r}"
        return False, "Syntax error detected"

    def _verify_syntax_content(self, content: bytes, language: str) -> Tuple[bool, Optional[str]]:
        if language not in LANGUAGE_MAP:
            return True, None
        parser = self._get_parser(language)
        if not parser:
            return True, None
        tree = parser.parse(content)
        if not tree.root_node.has_error:
            return True, None

        error_node = None
        def find_error(n):
            nonlocal error_node
            if n.type in ('ERROR', 'MISSING'):
                error_node = n
                return
            if not error_node:
                for child in n.children:
                    find_error(child)
        find_error(tree.root_node)

        if error_node:
            line = error_node.start_point[0] + 1
            col = error_node.start_point[1] + 1
            snippet = content[error_node.start_byte:error_node.end_byte].decode('utf-8', errors='replace').strip()
            return False, f"Syntax error at line {line}, column {col}: {snippet!r}"
        return False, "Syntax error detected"

    def _get_language_from_ext(self, file_path: str) -> str:
        ext = os.path.splitext(file_path)[1].lower()
        for lang, config in self.LANGUAGES.items():
            if ext in config.get('extensions', []):
                return lang
        return 'generic'

    def _get_backup_dir(self) -> str:
        backup_dir = core.sandbox_path(self.sandbox_path, ".backups")
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    async def _backup_file(self, file_path: str) -> Optional[str]:
        if not os.path.exists(file_path):
            return None
        try:
            backup_dir = self._get_backup_dir()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(file_path)
            backup_path = os.path.join(backup_dir, f"{basename}.{timestamp}.bak")
            shutil.copy2(file_path, backup_path)
            self._cleanup_old_backups(basename)
            return backup_path
        except Exception as e:
            self.log("coder", f"Backup failed: {e}")
            return None

    def _cleanup_old_backups(self, basename: str, max_count: int = None):
        max_count = max_count or self.config.get("limits", {}).get("backup_retention_count", 10)
        backup_dir = self._get_backup_dir()
        try:
            backups = [(os.path.getmtime(os.path.join(backup_dir, f)), os.path.join(backup_dir, f))
                       for f in os.listdir(backup_dir) if f.startswith(basename + ".") and f.endswith(".bak")]
            backups.sort(reverse=True)
            for _, path in backups[max_count:]:
                os.remove(path)
        except Exception as e:
            self.log("coder", f"Backup cleanup failed: {e}")

    def _walk_for_symbols(self, node, language: str, symbols: list, prefix: str = ""):
        lang_config = self.LANGUAGES.get(language, {})
        target_types = lang_config.get('symbol_types', {})
        if node.type in target_types:
            name = None
            for child in node.children:
                if child.type in ['identifier', 'property_identifier', 'name', 'field_identifier']:
                    try:
                        name = child.text.decode('utf-8')
                        break
                    except:
                        continue
            if name:
                full_name = f"{prefix}{name}"
                symbols.append({'name': full_name, 'type': target_types[node.type], 'line': node.start_point[0] + 1})
                for child in node.children:
                    self._walk_for_symbols(child, language, symbols, prefix=f"{full_name}.")
                return
        for child in node.children:
            self._walk_for_symbols(child, language, symbols, prefix=prefix)

    def _find_symbol_info(self, file_path: str, symbol_name: str, language: str) -> Optional[Tuple[Any, int]]:
        result = self._parse_file(file_path, language)
        if not result:
            return None
        tree, source_bytes = result
        target_node = None
        parts = symbol_name.split('.')

        def find_node(node, parts_to_match):
            nonlocal target_node
            if target_node or not parts_to_match:
                return
            current_part = parts_to_match[0]
            remaining_parts = parts_to_match[1:]
            lang_config = self.LANGUAGES.get(language, {})
            if node.type in lang_config.get('symbol_types', {}):
                for child in node.children:
                    if child.type in ['identifier', 'property_identifier', 'name', 'field_identifier']:
                        try:
                            if child.text.decode('utf-8') == current_part:
                                if not remaining_parts:
                                    target_node = node
                                    return
                                else:
                                    for next_child in node.children:
                                        find_node(next_child, remaining_parts)
                                return
                        except:
                            continue
            for child in node.children:
                find_node(child, parts_to_match)

        find_node(tree.root_node, parts)
        if target_node:
            return target_node, target_node.start_point[0] + 1
        return None

    def _find_symbol_line(self, file_path: str, symbol_name: str, language: str) -> Optional[int]:
        info = self._find_symbol_info(file_path, symbol_name, language)
        return info[1] if info else None

    async def list_project_folders(self, project_name: str, depth_limit: int = 5, max_files_per_folder: int = 50):
        """Get recursive tree view of a project. Use to navigate and understand project structure."""
        project_path = self._get_project_path(project_name)
        if not os.path.exists(project_path):
            return self.result("Error: project does not exist", success=False)

        def _build_tree(path: str, current_depth: int) -> dict:
            tree = {}
            files_counter = 0
            try:
                for entry in os.scandir(path):
                    if entry.is_file():
                        if files_counter < max_files_per_folder:
                            tree[entry.name] = None
                            files_counter += 1
                    elif entry.is_dir():
                        blacklist = self.config.get("limits", {}).get("folder_blacklist", [])
                        if entry.name in blacklist or entry.name.startswith('.'):
                            continue
                        folder_key = f"{entry.name}/"
                        tree[folder_key] = _build_tree(entry.path, current_depth + 1) if current_depth < depth_limit else {}
            except OSError:
                pass
            return tree

        try:
            return self.result(_build_tree(project_path, 0), success=True)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    async def list_project_subfolder(self, project_name: str, sub_path: str = ""):
        """List immediate contents of a project subfolder. Use to explore specific directories."""
        target_path = core.sandbox_path(self._get_project_path(project_name), sub_path)
        if not os.path.isdir(target_path):
            return self.result("Error: path does not exist or is not a directory", success=False)
        try:
            return self.result({"contents": os.listdir(target_path)}, success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def create_project(self, project_name: str):
        """Create a new project folder. Use to initialize a new project workspace."""
        if self.config.get("writing_mode") == "read-only":
            return self.result("Error: Coder is in read-only mode", success=False)
        base_path = self._get_project_path(project_name)
        if os.path.exists(base_path):
            return self.result("Project already exists!", False)
        try:
            os.makedirs(base_path, exist_ok=True)
            return self.result(f"Project '{project_name}' created.", success=True)
        except OSError as e:
            return self.result(f"Error creating project: {e}", success=False)

    async def get_template(self, template_name: str):
        """Retrieves the content of a coding template (see the templates listed in your system prompt)"""
        templates = os.listdir(self.templates_path)
        if template_name not in templates:
            return self.result("invalid template name. check your system prompt for template names!", success=False)

        # get template content and use it as the content for the new file
        with open(os.path.join(self.templates_path, template_name), encoding="utf-8") as f:
            content = f.read()

        return content

    async def create_file(self, project_name: str, file_path: str, content: str):
        """Creates a new file."""
        file_path_str = self._get_file_path(project_name, file_path)
        if os.path.exists(file_path_str):
            return self.result("Error: File already exists.", success=False)

        language = self._get_language_from_ext(file_path_str)
        is_valid, error = self._verify_syntax_content(content.encode('utf-8'), language)
        if not is_valid:
            return self.result(f"Error: {error}. File not written.", success=False)

        target_dir = os.path.dirname(file_path_str)
        os.makedirs(target_dir, exist_ok=True)
        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)
            return self.result(f"File created: {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def overwrite_file(self, project_name: str, file_path: str, content: str):
        """Completely replace a file's content. Only use as a last resort for massive refactors, and ensure you have the full file content before you use this."""
        file_path_str = self._get_file_path(project_name, file_path)
        language = self._get_language_from_ext(file_path_str)

        is_valid, error = self._verify_syntax_content(content.encode('utf-8'), language)
        if not is_valid:
            return self.result(f"Error: {error}. File not overwritten.", success=False)

        await self._backup_file(file_path_str)
        target_dir = os.path.dirname(file_path_str)
        os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)
            return self.result(f"File overwritten: {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def append_to_file(self, project_name: str, file_path: str, content: str):
        """Append content to the end of a file. Use for adding new code at the bottom."""
        file_path_str = self._get_file_path(project_name, file_path)
        target_dir = os.path.dirname(file_path_str)

        os.makedirs(target_dir, exist_ok=True)
        mode = 'a' if os.path.exists(file_path_str) else 'w'
        existing = b""
        if mode == 'a' and os.path.exists(file_path_str):
            with open(file_path_str, 'rb') as f:
                existing = f.read()
        combined = existing + content.encode('utf-8')
        if not combined.endswith(b'\n'):
            combined += b'\n'

        language = self._get_language_from_ext(file_path_str)
        is_valid, error = self._verify_syntax_content(combined, language)
        if not is_valid:
            return self.result(f"Error: {error}. Content not appended.", success=False)
        try:
            with open(file_path_str, 'ab' if mode == 'a' else 'wb') as f:
                f.write(b'\n' if mode == 'a' and existing and not existing.endswith(b'\n') else b'')
                f.write(content.encode('utf-8'))
                if not content.endswith('\n'):
                    f.write(b'\n')
            return self.result(f"Content appended to {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def execute(self, project_name: str, file_path: str, timeout: int = 30):
        """Execute a script file. Only use if code execution is explicitly enabled and requested."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        os.chmod(file_path_str, os.stat(file_path_str).st_mode | stat.S_IEXEC)

        try:
            proc = await asyncio.create_subprocess_exec(file_path_str, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
                stdout_str = stdout.decode('utf-8', errors='replace').strip()
                stderr_str = stderr.decode('utf-8', errors='replace').strip()
                if proc.returncode != 0:
                    return self.result(f"Error (exit code {proc.returncode}): {stderr_str or 'Unknown error'}", success=False)
                return self.result({"stdout": stdout_str, "stderr": stderr_str, "returncode": proc.returncode}, success=True)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return self.result(f"Error: Execution timed out after {timeout} seconds", success=False)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    async def get_outline(self, project_name: str, file_path: str, language: str = None):
        """List all symbols in a file. Always call this first to identify target symbols before reading or editing."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        if not language:
            language = self._get_language_from_ext(file_path_str)

        result = self._parse_file(file_path_str, language)
        if not result:
            return self.result("Error: failed to parse file", success=False)

        tree, _ = result
        symbols = []
        self._walk_for_symbols(tree.root_node, language, symbols)
        symbols.sort(key=lambda x: x['line'])
        return self.result({"symbols": [{"name": s["name"], "type": s["type"]} for s in symbols]}, success=True)

    def _check_if_symbol_is_class(self, node, language):
        # Check if the target is a class to prevent reading entire classes
        lang_config = self.LANGUAGES.get(language, {})
        target_types = lang_config.get('symbol_types', {})
        is_class = False

        # Iterate through the language config to see if this node type maps to 'class'
        for ts_type, type_str in target_types.items():
            if node.type == ts_type and type_str == 'class':
                return True

        return False

    async def get_symbol(self, project_name: str, file_path: str, symbol_name: str, language: str = None):
        """Read a specific symbol (function/class/method). Use after get_outline to inspect exact code before making changes."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        info = self._find_symbol_info(file_path_str, symbol_name, language)
        if not info:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)

        node, _ = info

        # if it's a class, return the outline instead
        if self._check_if_symbol_is_class(node, language):
            return self.result({"outline": await self.get_outline(project_name, file_path, language), "message": "This is an overview of all the symbols in the file. Read the ones you want to read using get_symbol."})

        parse_result = self._parse_file(file_path_str, language)
        if not parse_result:
            return self.result("Error: failed to parse file", success=False)

        _, source_bytes = parse_result
        found_code = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
        return found_code

    async def edit_symbol(self, project_name: str, file_path: str, symbol_name: str, new_content: str, language: str = None):
        """Replace a single symbol's implementation. Use for all modifications to existing functions, classes, or methods."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        if not language:
            language = self._get_language_from_ext(file_path_str)
        info = self._find_symbol_info(file_path_str, symbol_name, language)

        if not info:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)
        node, _ = info

        # if it's a class, outright reject the edit
        if self._check_if_symbol_is_class(node, language):
            return self.result("Error: target symbol is a class. Do NOT edit entire classes. Target class methods instead - use get_outline() on the class to see them.", success=False)

        parse_result = self._parse_file(file_path_str, language)
        if not parse_result:
            return self.result("Error: failed to parse file", success=False)

        _, source_bytes = parse_result
        new_content_bytes = new_content.encode('utf-8')
        updated_bytes = source_bytes[:node.start_byte] + new_content_bytes + source_bytes[node.end_byte:]
        is_valid, error = self._verify_syntax_content(updated_bytes, language)

        if not is_valid:
            return self.result(f"Error: {error}. Edit not applied.", success=False)

        await self._backup_file(file_path_str)
        with open(file_path_str, 'wb') as f:
            f.write(updated_bytes)
        return self.result(f"Symbol '{symbol_name}' edited in {file_path}", success=True)

    async def add_symbol_before(self, project_name: str, file_path: str, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """Insert a new symbol before an existing one. Use for adding new functions, methods, or classes."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        if not language:
            language = self._get_language_from_ext(file_path_str)

        info = self._find_symbol_info(file_path_str, target_symbol_name, language)
        if not info:
            return self.result(f"Error: symbol '{target_symbol_name}' not found", success=False)
        target_node, _ = info
        parse_result = self._parse_file(file_path_str, language)
        if not parse_result:
            return self.result("Error: failed to parse file", success=False)

        _, source_bytes = parse_result
        insert_pos = target_node.start_byte
        new_symbol_bytes = content_body.encode('utf-8')
        if not new_symbol_bytes.endswith(b'\n'):
            new_symbol_bytes += b'\n'
        if insert_pos > 0 and source_bytes[insert_pos-1:insert_pos] != b'\n':
            new_symbol_bytes += b'\n'
        updated_bytes = source_bytes[:insert_pos] + new_symbol_bytes + source_bytes[insert_pos:]
        is_valid, error = self._verify_syntax_content(updated_bytes, language)

        if not is_valid:
            return self.result(f"Error: {error}. Addition not applied.", success=False)

        await self._backup_file(file_path_str)
        with open(file_path_str, 'wb') as f:
            f.write(updated_bytes)
        return self.result(f"Symbol '{name}' added before '{target_symbol_name}'", success=True)

    async def add_symbol_after(self, project_name: str, file_path: str, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """Insert a new symbol after an existing one. Use for adding new functions, methods, or classes."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        if not language:
            language = self._get_language_from_ext(file_path_str)

        info = self._find_symbol_info(file_path_str, target_symbol_name, language)
        if not info:
            return self.result(f"Error: symbol '{target_symbol_name}' not found", success=False)

        target_node, _ = info
        parse_result = self._parse_file(file_path_str, language)
        if not parse_result:
            return self.result("Error: failed to parse file", success=False)

        _, source_bytes = parse_result
        insert_pos = target_node.end_byte
        new_symbol_bytes = content_body.encode('utf-8')
        if not new_symbol_bytes.startswith(b'\n'):
            new_symbol_bytes = b'\n' + new_symbol_bytes
        if not new_symbol_bytes.endswith(b'\n'):
            new_symbol_bytes += b'\n'
        updated_bytes = source_bytes[:insert_pos] + new_symbol_bytes + source_bytes[insert_pos:]
        is_valid, error = self._verify_syntax_content(updated_bytes, language)

        if not is_valid:
            return self.result(f"Error: {error}. Addition not applied.", success=False)

        await self._backup_file(file_path_str)
        with open(file_path_str, 'wb') as f:
            f.write(updated_bytes)
        return self.result(f"Symbol '{name}' added after '{target_symbol_name}'", success=True)

    async def delete_symbol(self, project_name: str, file_path: str, symbol_name: str, language: str = None):
        """Remove a single symbol. Use to delete functions, classes, or methods."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        if not language:
            language = self._get_language_from_ext(file_path_str)

        info = self._find_symbol_info(file_path_str, symbol_name, language)
        if not info:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)

        node, _ = info

        # if it's a class, outright reject the edit
        if self._check_if_symbol_is_class(node, language):
            return self.result("Error: target symbol is a class. Do NOT edit entire classes. Target class methods instead - use get_outline() on the class to see them.", success=False)

        parse_result = self._parse_file(file_path_str, language)
        if not parse_result:
            return self.result("Error: failed to parse file", success=False)
        _, source_bytes = parse_result
        updated_bytes = source_bytes[:node.start_byte] + source_bytes[node.end_byte:]
        is_valid, error = self._verify_syntax_content(updated_bytes, language)

        if not is_valid:
            return self.result(f"Error: {error}. Deletion not applied.", success=False)

        await self._backup_file(file_path_str)
        with open(file_path_str, 'wb') as f:
            f.write(updated_bytes)
        return self.result(f"Symbol '{symbol_name}' deleted from {file_path}", success=True)

    async def read_file(self, project_name: str, file_path: str, limit: int = None, offset: int = None):
        """Read file content with pagination. ONLY use if symbol-level reading fails or the file lacks parseable symbols."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        size_ok, size_error = self._check_file_size(file_path_str)
        if not size_ok:
            return self.result(f"Error: {size_error}", success=False)
        try:
            with open(file_path_str, "r", encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)
            max_lines = self.config.get("limits", {}).get("max_read_lines", 1000)
            start_idx = max(0, (offset or 1) - 1)
            end_idx = min(start_idx + (limit or max_lines), total_lines)

            if end_idx - start_idx > max_lines:
                end_idx = start_idx + max_lines

            selected_lines = lines[start_idx:end_idx]
            result = "".join(selected_lines)
            response = result

            if end_idx < total_lines:
                response += f"\n[Output truncated. {total_lines - end_idx} lines remain.]"
            return response
        except OSError as e:
            return self.result(f"Error reading file: {e}", success=False)

    async def search(self, project_name: str, file_path: str, query: str, context_lines: int = 5, max_matches: int = 10):
        """Search for text within a single file using regex patterns. Use for locating exact strings when symbols are unavailable."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            matches, num_lines = [], len(lines)
            
            # Try to compile as regex first, fall back to simple substring matching
            compiled_pattern = None
            try:
                compiled_pattern = regex.compile(query, regex.IGNORECASE)
            except regex.error:
                # Not a valid regex, use simple substring matching (backward compatible)
                query_lower = query.lower()
            
            # placing rstrip string to avoid redefining it for every single line when it remains constant; Windows doesn't allow f-strings to have backlashes but is fine with them being in a predefined string
            rstrip_string = '\n\r'
            for i, line in enumerate(lines):
                if len(matches) >= max_matches:
                    break
                if compiled_pattern:
                    # regex library has native timeout support to prevent ReDoS
                    try:
                        match_found = compiled_pattern.search(line, timeout=self.regex_timeout)
                    except regex.error as e:
                        if "timed out" in str(e).lower():
                            self.log("coder", f"Regex timed out on {file_path}, line {i+1} - possible ReDoS, skipping")
                        continue
                    if match_found:
                        snippet = [f"--- Match at line {i+1} ---"]
                        for j in range(max(0, i - context_lines), min(num_lines, i + context_lines + 1)):
                            marker = "  <-- MATCH" if j == i else ""
                            snippet.append(f"{j+1:4}: {lines[j].rstrip(rstrip_string)}{marker}")
                        matches.append("\n".join(snippet))
                else:
                    if query_lower in line.lower():
                        snippet = [f"--- Match at line {i+1} ---"]
                        for j in range(max(0, i - context_lines), min(num_lines, i + context_lines + 1)):
                            marker = "  <-- MATCH" if j == i else ""
                            snippet.append(f"{j+1:4}: {lines[j].rstrip(rstrip_string)}{marker}")
                        matches.append("\n".join(snippet))
            return self.result({"matches": len(matches), "file": file_path, "results": "\n\n".join(matches)}, success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def replace(self, project_name: str, file_path: str, query: str, replacement: str):
        """Replace all occurrences of a string in a file. ONLY use if symbol-level replacement is impossible."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                content = f.read()
            count = content.count(query)
            if count > 0:
                new_content = content.replace(query, replacement)
                language = self._get_language_from_ext(file_path_str)
                is_valid, error = self._verify_syntax_content(new_content.encode('utf-8'), language)
                if not is_valid:
                    return self.result(f"Error: {error}. Replacement not applied.", success=False)
                await self._backup_file(file_path_str)
                with open(file_path_str, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                return self.result({"success": True, "message": f"Replaced {count} occurrence(s)", "file": file_path, "replacements": count}, success=True)
            return self.result({"success": True, "message": "No matches found.", "file": file_path}, success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def grep(self, project_name: str, path: str = "", pattern: str = "", case_sensitive: bool = False, max_results: int = None):
        """Search for text across files using regex patterns. Returns code snippets with symbol context. Use `get_outline` and `get_symbol` for full code views."""
        search_dir = core.sandbox_path(self._get_project_path(project_name), path) if path else self._get_project_path(project_name)
        if not os.path.isdir(search_dir):
            return self.result("Error: search directory does not exist", success=False)
        max_results = max_results or self.config.get("limits", {}).get("max_grep_results", 50)
        
        # Get folder blacklist from config
        folder_blacklist = set(self.config.get("limits", {}).get("folder_blacklist", ["venv", "__pycache__"]))

        try:
            # Compile the regex pattern with native timeout support
            flags = 0 if case_sensitive else regex.IGNORECASE
            try:
                compiled_pattern = regex.compile(pattern, flags)
            except regex.error as e:
                return self.result(f"Error: invalid regex pattern - {e}", success=False)

            results, total_matches, file_count = [], 0, 0
            symbol_map = {}
            lines = []

            for root, dirs, files in os.walk(search_dir):
                # Filter out blacklisted and hidden directories using config
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in folder_blacklist]
                for filename in sorted(files):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, search_dir)
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ('.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.db', '.sqlite', '.png', '.jpg', '.gif', '.pdf'):
                        continue

                    language = self._get_language_from_ext(filepath)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            lines = f.readlines()

                        # Map 0-based line indices to symbol names using the same prefix logic as _walk_for_symbols
                        symbol_map = {}
                        if language != 'generic' and language in self.LANGUAGES:
                            parse_result = self._parse_file(filepath, language)
                            if parse_result:
                                tree, _ = parse_result
                                lang_config = self.LANGUAGES[language]
                                target_types = lang_config.get('symbol_types', {})

                                def collect_symbols(node, prefix: str):
                                    if node.type in target_types:
                                        sym_name = None
                                        for c in node.children:
                                            if c.type in ['identifier', 'property_identifier', 'name', 'field_identifier']:
                                                try:
                                                    sym_name = c.text.decode('utf-8')
                                                    break
                                                except:
                                                    pass
                                        if sym_name:
                                            full_name = f"{target_types[node.type]}: {prefix}{sym_name}"
                                            for ln in range(node.start_point[0], node.end_point[0] + 1):
                                                symbol_map[ln] = full_name
                                            new_prefix = f"{prefix}{sym_name}."
                                            for child in node.children:
                                                collect_symbols(child, new_prefix)
                                            return
                                    for child in node.children:
                                        collect_symbols(child, prefix)

                                collect_symbols(tree.root_node, "")

                        for i, line in enumerate(lines):
                            if total_matches >= max_results: break
                            # regex library has native timeout support to prevent ReDoS
                            try:
                                match_found = compiled_pattern.search(line, timeout=self.regex_timeout)
                            except regex.error as e:
                                if "timed out" in str(e).lower():
                                    self.log("coder", f"Regex timed out on {filepath}, line {i+1} - possible ReDoS, skipping")
                                continue
                            if match_found:
                                sym = symbol_map.get(i, "Global")
                                snippet = line.rstrip('\n')[:200]
                                results.append(f"[{rel_path}] [{sym}] {snippet}")
                                total_matches += 1
                    except Exception:
                        continue
                    file_count += 1
                    if total_matches >= max_results: break
                if total_matches >= max_results: break

            return self.result({"pattern": pattern, "matches": len(results), "truncated": total_matches > max_results, "results": results}, success=True)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)


    async def find_files(self, project_name: str, pattern: str = "*", path: str = "", file_type: str = "any"):
        """Find files matching a glob pattern. Searches recursively through the project directory structure."""
        search_dir = core.sandbox_path(self._get_project_path(project_name), path) if path else self._get_project_path(project_name)
        if not os.path.exists(search_dir):
            return self.result("Error: search directory does not exist", success=False)
        
        # Get folder blacklist from config
        folder_blacklist = set(self.config.get("limits", {}).get("folder_blacklist", ["venv", "__pycache__"]))
        
        try:
            # Normalize the pattern - ensure it supports recursive search
            # If pattern doesn't contain **, prefix with **/ for recursive matching
            normalized_pattern = pattern
            if '**' not in pattern and '/' not in pattern:
                normalized_pattern = f"**/{pattern}"
            elif '/' in pattern and '**' not in pattern:
                normalized_pattern = f"**/{pattern}"
            
            matches = glob_module.glob(os.path.join(search_dir, normalized_pattern), recursive=True)
            results = []
            for match in matches:
                rel_path = os.path.relpath(match, search_dir)
                # Skip if it's a hidden directory/file
                if any(part.startswith('.') for part in rel_path.split(os.sep)):
                    continue
                # Skip if any path component is in the blacklist
                path_parts = rel_path.split(os.sep)
                if any(part in folder_blacklist for part in path_parts):
                    continue
                if file_type == "directory" and not os.path.isdir(match): continue
                if file_type == "file" and not os.path.isfile(match): continue
                try:
                    core.sandbox_path(search_dir, rel_path)
                    results.append(rel_path)
                except ValueError:
                    continue
            return self.result({"pattern": pattern, "count": len(results), "files": sorted(results)}, success=True)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    async def list_backups(self, project_name: str, file_path: str) -> dict:
        """List available backups for a file. Use to recover previous versions before major edits."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return {"success": False, "error": "File does not exist"}
        try:
            backup_dir = self._get_backup_dir()
            basename = os.path.basename(file_path_str)
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith(basename + ".") and f.endswith(".bak"):
                    full_path = os.path.join(backup_dir, f)
                    backups.append({"filename": f, "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(full_path)))})
            backups.sort(key=lambda x: x["timestamp"], reverse=True)
            for i, b in enumerate(backups):
                b["index"] = i
            return {"success": True, "backups": backups}
        except OSError as e:
            return {"success": False, "error": f"List backups failed: {e}"}

    async def restore_backup(self, project_name: str, file_path: str, version_index: int = 0) -> dict:
        """Restore a file from a backup."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return {"success": False, "error": "File does not exist"}
        try:
            backup_dir = self._get_backup_dir()
            basename = os.path.basename(file_path_str)
            backups = sorted([(os.path.getmtime(os.path.join(backup_dir, f)), os.path.join(backup_dir, f))
                              for f in os.listdir(backup_dir) if f.startswith(basename + ".") and f.endswith(".bak")], reverse=True)
            if not backups:
                return {"success": False, "error": "No backups found"}
            if version_index < 0 or version_index >= len(backups):
                return {"success": False, "error": f"Invalid version index."}
            shutil.copy2(backups[version_index][1], file_path_str)
            return {"success": True, "message": f"Restored from {os.path.basename(backups[version_index][1])}"}
        except OSError as e:
            return {"success": False, "error": f"Restore failed: {e}"}

    async def on_system_prompt(self) -> str:
        """Generate system prompt additions."""
        output = ""
        coding_style = self.config.get("coding_style")
        if coding_style:
            output += f"\n## Coding Style\n{coding_style}\n"

        # Dynamically detect if symbol-level tools are active
        reading_mode = self.config.get("reading_mode")
        writing_mode = self.config.get("writing_mode")

        if reading_mode in ("symbols", "both") or writing_mode in ("symbols", "both"):
            supported_langs = ", ".join(sorted(self.LANGUAGES.keys()))
            output += f"""
## Tool Selection Strategy

The coder uses treesitter to automatically parse source code files so that you can target specific classes and functions and efficiently make surgical edits.
Surgical precision is enabled for: {supported_langs}

For these languages, these instructions apply:

1.  **Discovery Phase (Mandatory):** Before reading or editing, you must locate the target code.
    -   **Search:** Use `grep` to find code snippets across files.
    -   **List:** Use `get_outline` to see the structure of a specific file.
2.  **Surgical Precision (Preferred):**
    -   **Reading:** Use `get_symbol` to read specific functions/classes. **Do not read the whole file just to see one function.**
    -   **Editing:** Use `edit_symbol` for precise changes.
3.  **File-Level (Exceptions Only):** Use `read_file`, `edit`, `replace` ONLY when:
    -   You need to inspect imports, top-level constants, or comments outside symbols.
    -   The change involves moving code between symbols (e.g. moving a function to a new class).
    -   Tree-sitter fails to parse a symbol.

**Efficiency Note:** Using symbol-level tools is significantly more efficient for your context window. Reading entire files is considered a fallback strategy and should be avoided unless you are performing a full-file refactor.

## Examples
✅ CORRECT: "I'll use `grep` to find the function definition first." -> `grep`
✅ CORRECT: "I'll get the outline to see the class structure." -> `get_outline`
✅ CORRECT: "I need to see the imports, so I'll read the file." -> `read_file`
❌ WRONG: "I'll read the file to understand the function." -> `read_file` (Should use `get_symbol`)
❌ WRONG: "I'll edit the file directly." -> `edit` (Should use `edit_symbol`)
""".strip()

        if self.config.get("add_project_list_to_system_prompt"):
            try:
                projects = [f for f in os.listdir(self.sandbox_path) if os.path.isdir(os.path.join(self.sandbox_path, f))]
                output += "\n## Available Projects\n" + "\n".join(f"- {p}" for p in sorted(projects)) + "\n" if projects else "\n## Available Projects\nNo projects exist yet.\n"
            except OSError as e:
                output += f"\n## Available Projects\nCould not list projects: {e}\n"


        templates = os.listdir(self.templates_path)
        if templates:
            output += f"\n## Available templates:\n" +"\n".join(f"- {template}" for template in sorted(templates))

        return output
