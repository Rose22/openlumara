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
import modules.sandboxed_files
from typing import List, Dict, Any, Optional, Union

# --- Improved Tree-sitter Setup ---
HAS_TREE_SITTER = False
LANGUAGE_MAP = {}
loaded_languages = []
disabled_reason = ""

try:
    import tree_sitter
    from tree_sitter import Language, Parser
    HAS_TREE_SITTER = True

    def _try_import_lang(mod_name, lang_key):
        """Attempts to import a language parser and add it to the map."""
        try:
            mod = importlib.import_module(mod_name)
            LANGUAGE_MAP[lang_key] = Language(mod.language())
            return True
        except (ImportError, AttributeError):
            return False

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

    for mod_name, lang_key in languages_to_attempt:
        if _try_import_lang(mod_name, lang_key):
            loaded_languages.append(lang_key)

except ImportError as e:
    HAS_TREE_SITTER = False
    disabled_reason = f"Tree-sitter core library missing: {e}"
except Exception as e:
    HAS_TREE_SITTER = False
    disabled_reason = f"Unexpected error during setup: {e}"

class Coder(modules.sandboxed_files.SandboxedFiles):
    """Allows your AI to write, edit and test code for you."""

    settings = {
        "coding_style": "Write clean, well-commented code. Do not include your reasoning inside final code.",
        "sandbox_folder": "~/coder",
        "read-only": False,
        "folder_blacklist": ["venv"],
        "allow_function_adding": True,
        "allow_function_editing": True,
        "allow_function_deleting": True,
        "allow_project_creation": True,
        "allow_file_creation": True,
        "allow_full_file_reads": False,
        "allow_full_file_overwrites": False,
        "allow_code_execution": False
    }

    # Consolidated language configuration with all metadata in one place
    LANGUAGES = {
        'python': {
            'extensions': ['.py'],
            'body_type': 'indentation',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*[a-zA-Z_][a-zA-Z0-9_]*\s*[:=]', 'variable'),
            ],
            'symbol_types': {
                'class_definition': 'class',
                'function_definition': 'function',
                'assignment': 'variable',
            }
        },
        'javascript': {
            'extensions': ['.js', '.jsx'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', 'variable'),
                (r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'function_declaration': 'function',
                'method_definition': 'method',
                'arrow_function': 'function',
                'variable_declarator': 'variable',
            }
        },
        'typescript': {
            'extensions': ['.ts', '.tsx'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*(?:const|let|var)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*=', 'variable'),
                (r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'function_declaration': 'function',
                'method_definition': 'method',
                'variable_declarator': 'variable',
            }
        },
        'html': {
            'extensions': ['.html', '.htm'],
            'body_type': 'brace',
            'outline_patterns': [],
            'symbol_types': {}
        },
        'css': {
            'extensions': ['.css'],
            'body_type': 'brace',
            'outline_patterns': [],
            'symbol_types': {}
        },
        'cpp': {
            'extensions': ['.cpp', '.c', '.h', '.hpp', '.cc'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*struct\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'struct'),
                (r'^\s*[\w:<>\*]+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)', 'function'),
            ],
            'symbol_types': {
                'class_specifier': 'class',
                'struct_specifier': 'struct',
                'function_definition': 'function',
            }
        },
        'c-sharp': {
            'extensions': ['.cs'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:public|private|protected|internal|static|\s)+\w+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'method_declaration': 'method',
            }
        },
        'rust': {
            'extensions': ['.rs'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*struct\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'struct'),
                (r'^\s*enum\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'enum'),
                (r'^\s*fn\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'symbol_types': {
                'struct_item': 'struct',
                'enum_item': 'enum',
                'fn': 'function',
                'impl_item': 'impl',
            }
        },
        'ruby': {
            'extensions': ['.rb'],
            'body_type': 'indentation',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*module\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'module'),
                (r'^\s*def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'symbol_types': {
                'class': 'class',
                'module': 'module',
                'def': 'function',
            }
        },
        'go': {
            'extensions': ['.go'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*type\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+struct', 'struct'),
                (r'^\s*func\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'symbol_types': {
                'type_declaration': 'struct',
                'function_declaration': 'function',
                'method_declaration': 'method',
            }
        },
        'java': {
            'extensions': ['.java'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:public|protected|private|static|\s)+\w+\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'method_declaration': 'method',
                'constructor_declaration': 'method',
            }
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.sandbox_path

        if HAS_TREE_SITTER:
            if not loaded_languages:
                core.log("coder", "Tree-sitter installed but NO language parsers found.")
            else:
                core.log("coder", f"Tree-sitter ENABLED. Languages: {loaded_languages}")
        else:
            core.log("coder", f"Tree-sitter DISABLED. Reason: {disabled_reason}")

        # Disable tools based on config
        if self.config.get("read-only"):
            self.disabled_tools.extend([
                "add_symbol_before", "add_symbol_after", "edit_symbol",
                "delete_symbol", "create_project", "create_file",
                "overwrite_file", "execute"
            ])

        if not self.config.get("allow_function_adding"):
            self.disabled_tools.extend(["add_symbol_before", "add_symbol_after"])

        if not self.config.get("allow_function_editing"):
            self.disabled_tools.append("edit_symbol")

        if not self.config.get("allow_function_deleting"):
            self.disabled_tools.append("delete_symbol")

        if not self.config.get("allow_project_creation"):
            self.disabled_tools.append("create_project")

        if not self.config.get("allow_file_creation"):
            self.disabled_tools.append("create_file")

        if not self.config.get("allow_full_file_overwrites"):
            self.disabled_tools.append("overwrite_file")

        if not self.config.get("allow_code_execution"):
            self.disabled_tools.append("execute")

    def _get_language_from_ext(self, file_path_str: str) -> str:
        ext = os.path.splitext(file_path_str)[1].lower()
        for lang, config in self.LANGUAGES.items():
            if ext in config.get('extensions', []):
                return lang
        return 'generic'

    def _validate_content(self, content: str, context: str = "content") -> tuple:
        """
        Validates that content is not double-escaped or malformed.
        Returns (is_valid, cleaned_content, error_message).
        """
        if not isinstance(content, str):
            return False, content, f"{context} must be a string"

        # Check for escaped characters that indicate double-encoding
        has_escaped_quotes = '\\"' in content or "\\\"\"" in content or "\\'''" in content
        has_literal_newlines = r'\n' in content  # The literal backslash-n sequence

        # Also check if it looks like it was JSON-encoded
        looks_like_json_string = (
            (content.startswith('"') and content.endswith('"')) or
            (content.startswith("'") and content.endswith("'"))
        ) and (has_escaped_quotes or has_literal_newlines)

        if has_escaped_quotes or (has_literal_newlines and '\n' not in content[:500]):
            core.log("coder", f"WARNING: {context} contains escaped characters. Attempting to decode.")

            try:
                import codecs
                # Try to decode escape sequences
                decoded = codecs.decode(content, 'unicode_escape')
                # If the decoded version has actual newlines where there were \n, use it
                if '\n' in decoded and r'\n' in content[:200]:
                    core.log("coder", f"Successfully decoded escaped content for {context}")
                    return True, decoded, None
            except Exception as e:
                core.log("coder", f"Failed to decode escaped content: {e}")

            # If decoding failed, give a clear error
            if has_escaped_quotes and has_literal_newlines:
                return False, content, (
                    f"{context} appears to be double-escaped with both escaped quotes (\\\") "
                    f"and escaped newlines (\\n). You must pass raw code with actual quotes "
                    f"and actual line breaks, NOT escaped sequences."
                )
            elif has_escaped_quotes:
                return False, content, (
                    f"{context} contains escaped quotes (\\\"). "
                    f"Pass raw code with actual quote characters."
                )
            elif has_literal_newlines:
                return False, content, (
                    f"{context} contains escaped newlines (\\n as text, not actual newlines). "
                    f"Pass raw code with actual line breaks."
                )

        if looks_like_json_string:
            core.log("coder", f"WARNING: {context} appears to be a JSON string literal. Attempting to decode.")
            try:
                import json
                decoded = json.loads(content)
                if isinstance(decoded, str):
                    return True, decoded, None
            except:
                return False, content, (
                    f"{context} appears to be a JSON-encoded string. "
                    f"Pass raw source code directly, not a JSON string literal."
                )

        return True, content, None

    async def on_system_prompt(self):
        """Generates the system prompt with tool usage guidelines."""
        output = """
## Code Editing Tool Usage

### Tool Selection Priority

When working with code files, you MUST use tools in this order:

1. **get_outline** - Call this first to see all symbols (classes, functions) in a file.
2. **get_symbol** - Use this to retrieve specific code by symbol name. PRIMARY reading method.
3. **edit_symbol / add_symbol_before / add_symbol_after / delete_symbol** - Modify code precisely.
4. **read_file** - LAST RESORT only. Do not use for normal code reading.
5. **overwrite_file** - Only for complete file restructuring.
""".strip()

        coding_style = self.config.get("coding_style")
        if coding_style:
            output += f"\n## Coding Style\n{coding_style}\n\n"

        try:
            file_list = os.listdir(self.sandbox_path)
            project_list = [f for f in file_list if os.path.isdir(os.path.join(self.sandbox_path, f))]

            output += "## Projects in Sandbox\n"
            if not project_list:
                output += "No projects exist. Use `create_project` to create one.\n"
            else:
                for name in project_list:
                    output += f"- {name}\n"
        except Exception as e:
            output += f"Could not list projects: {e}\n"

        if HAS_TREE_SITTER:
            output += f"\n## Parser Support\nTree-sitter parsing enabled for: {', '.join(loaded_languages)}\n"
        else:
            output += f"\n## Parser Support\nTree-sitter disabled: {disabled_reason}\n"

        return output

    def _get_project_path(self, name: str):
        return self._get_sandbox_path(name)

    def _get_file_path(self, project_name: str, file_path: list):
        rel_path = os.path.join(project_name, *file_path)
        return self._get_sandbox_path(rel_path)

    async def list_full_project_tree(self, project_name: str, depth_limit: int = 3):
        """
        Returns a recursive tree representation of the project structure.
        Use this to understand the overall project layout before diving into specific files.
        """
        project_path = self._get_project_path(project_name)
        if not os.path.exists(project_path):
            return self.result("project does not exist", False)

        def _build_tree(path, current_depth):
            if not os.path.isdir(path):
                return os.path.basename(path)

            contents = []
            try:
                for entry in os.scandir(path):
                    if entry.is_file():
                        contents.append(entry.name)
                    elif entry.is_dir():
                        if entry.name in self.config.get("folder_blacklist", []):
                            continue
                        if entry.name.startswith('.'):
                            continue
                        if current_depth < depth_limit:
                            contents.append({entry.name: _build_tree(entry.path, current_depth + 1)})
                        else:
                            contents.append(f"{entry.name}/")
            except Exception:
                pass

            return {"root": contents} if current_depth == 0 else contents

        try:
            tree = _build_tree(project_path, 0)
            return self.result(tree)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def list_project_folder(self, project_name: str, sub_path: list = None):
        """
        Lists the immediate contents of a specific path within a project (non-recursive).
        """
        sub_path = sub_path or []
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

    async def create_project(self, project_name: str):
        """
        Creates a new project directory in the sandbox.
        """
        if not self.config.get("allow_project_creation"):
            return self.result("Project creation is disabled.", False)

        base_path = self._get_project_path(project_name)
        try:
            os.makedirs(base_path, exist_ok=True)
            return self.result(f"Project '{project_name}' created.")
        except OSError as e:
            return self.result(f"Error creating project: {e}", False)

    async def create_file(self, project_name: str, file_path: list, content: str):
        """
        Creates a new file within a project.

        IMPORTANT: The `content` parameter should be raw source code with actual newlines
        and quotes, NOT a JSON-encoded string literal.

        Args:
            project_name: Name of the project.
            file_path: List of path components (e.g., ["src", "main.py"]).
            content: Raw source code content.
        """
        if not self.config.get("allow_file_creation"):
            return self.result("File creation is disabled", False)

        # Validate content
        is_valid, cleaned_content, error = self._validate_content(content, "content")
        if not is_valid and error:
            return self.result(f"Content validation error: {error}", False)
        content = cleaned_content

        file_path_str = self._get_file_path(project_name, file_path)

        if os.path.exists(file_path_str):
            return self.result(f"file already exists at {file_path_str}", False)

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)
            return self.result(True)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def read_file(self, project_name: str, file_path: list):
        """
        Reads an entire file.

        WARNING: This tool should be used as a LAST RESORT only!
        Prefer using get_outline() + get_symbols() to read specific code blocks.
        Reading entire files wastes tokens and floods your context.
        """
        if not self.config.get("allow_full_file_reads"):
            return self.result("Full file reading is disabled. Use get_symbol!", False)

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        try:
            with open(file_path_str, "r", encoding='utf-8') as f:
                result = f.read()
            return result # return raw string to avoid escaping content
        except Exception as e:
            return self.result(f"error reading file: {e}", False)

    async def overwrite_file(self, project_name: str, file_path: list, content: str):
        """
        Completely overwrites an existing file with new content.

        IMPORTANT: The `content` parameter should be raw source code with actual newlines
        and quotes, NOT a JSON-encoded string literal.
        """
        if not self.config.get("allow_full_file_overwrites"):
            return self.result("File overwriting is disabled. Use edit_symbol!", False)

        # Validate content
        is_valid, cleaned_content, error = self._validate_content(content, "content")
        if not is_valid and error:
            return self.result(f"Content validation error: {error}", False)
        content = cleaned_content

        file_path_str = self._get_file_path(project_name, file_path)

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)
            return self.result(True)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def execute(self, project_name: str, file_path: list, timeout: int = 30):
        """
        Executes a file within a project.
        """
        if not self.config.get("allow_code_execution"):
            return self.result("Code execution is disabled for security.", False)

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
                stdout_str = stdout.decode('utf-8', errors='replace').strip()
                stderr_str = stderr.decode('utf-8', errors='replace').strip()

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

    async def get_outline(self, project_name: str, file_path: list, language: str = None):
        """
        Returns a list of symbols (classes, functions, etc.) in a file.
        USE THIS FIRST to understand what's in a file before reading specific symbols.

        Returns a list of dicts with 'name' and 'type' keys.
        Example: [{"name": "MyClass", "type": "class"}, {"name": "my_function", "type": "function"}]
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
                return self.result([{"name": s["name"], "type": s["type"]} for s in symbols])
            except Exception as e:
                core.log("coder", f"Tree-sitter failed, falling back to regex: {e}")

        # 2. Fallback to Regex
        lang_config = self.LANGUAGES.get(language, {})
        patterns = lang_config.get('outline_patterns', [
            (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
            (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
        ])

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            outline = []
            for idx, line in enumerate(lines):
                for pattern, sym_type in patterns:
                    match = re.search(pattern, line)
                    if match:
                        outline.append({"name": match.group(1), "type": sym_type})
                        break
            return self.result(outline)
        except Exception as e:
            return self.result(f"error: {e}", False)

    def _walk_for_symbols(self, node, language, symbols, prefix=""):
        """Recursive tree walker for Tree-sitter nodes."""
        lang_config = self.LANGUAGES.get(language, {})
        target_types = lang_config.get('symbol_types', {})

        if node.type in target_types:
            sym_type = target_types[node.type]
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
                symbols.append({
                    'name': full_name,
                    'type': sym_type,
                    'line': node.start_point[0] + 1
                })
                for child in node.children:
                    self._walk_for_symbols(child, language, symbols, prefix=f"{full_name}.")
                return

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
                    return target_node.start_point[0] + 1
            except Exception:
                pass

        # 2. Fallback to Regex - FIXED: now uses correct config source
        parts = symbol_name.split('.')
        last_part = parts[-1]
        lang_config = self.LANGUAGES.get(language, {})
        patterns = lang_config.get('outline_patterns', [
            (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
            (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
        ])

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                for idx, line in enumerate(f):
                    for pattern, sym_type in patterns:
                        match = re.search(pattern, line)
                        if match and match.group(1) == last_part:
                            return idx + 1
        except Exception:
            pass

        return None

    async def get_symbol(self, project_name: str, file_path: list, symbol_name: str, language: str = None):
        """
        Returns the code block for a symbol by name.

        THIS IS THE PREFERRED WAY TO READ CODE.
        Use this instead of read_file() to get only the code you need.

        Args:
            symbol: a symbol name (e.g. "MyClass", "my_function", "MyClass.my_method")

        Returns:
            The code of the symbol as a string
        """
        results = {}
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result({"error": "file does not exist"}, False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        name = symbol_name

        line_number = self._find_symbol_line(file_path_str, name, language)
        if not line_number:
            return self.result(f"symbol '{name}' not found", False)

        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        lang_config = self.LANGUAGES.get(language, {})
                        if node.type in lang_config.get('symbol_types', {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    found_code = source_bytes[best_node.start_byte:best_node.end_byte].decode('utf-8')
                    return found_code
            except Exception as e:
                core.log("coder", f"Tree-sitter failed for get_symbol: {e}")

        # 2. Fallback to indentation/brace logic
        lang_config = self.LANGUAGES.get(language, {})
        body_type = lang_config.get('body_type', 'brace')

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
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
                    if not line.strip() or line.strip().startswith('#'):
                        continue
                    if get_indent(line) <= base_indent:
                        break
                    end_idx = i + 1
                body_lines = lines[start_idx:end_idx]
            else:
                brace_found = False
                start_brace_idx = -1
                for i in range(start_idx, len(lines)):
                    if '{' in lines[i]:
                        start_brace_idx = i
                        brace_found = True
                        break

                if not brace_found:
                    return "".join(lines[start_idx:start_idx + 1])

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

            return "".join(body_lines)
        except Exception as e:
            return self.result(f"error: {e}", False)

    async def edit_symbol(self, project_name: str, file_path: list, symbol_name: str, new_content: str, language: str = None):
        """
        Replaces the content of a symbol with new content.

        IMPORTANT: The `new_content` parameter should be raw source code with actual
        newlines and quotes, NOT a JSON-encoded string literal.

        Args:
            symbol_name: Name of the symbol to edit (e.g., "MyClass.my_method")
            new_content: The new source code for the symbol
        """
        if not self.config.get("allow_function_editing"):
            return self.result("Symbol editing is disabled.", False)

        # Validate content
        is_valid, cleaned_content, error = self._validate_content(new_content, "new_content")
        if not is_valid and error:
            return self.result(f"Content validation error: {error}", False)
        new_content = cleaned_content.strip()

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"symbol '{symbol_name}' not found", False)

        # 1. Try Tree-sitter for precise byte-level replacement
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        lang_config = self.LANGUAGES.get(language, {})
                        if node.type in lang_config.get('symbol_types', {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    new_content_bytes = new_content.encode('utf-8')
                    updated_bytes = source_bytes[:best_node.start_byte] + new_content_bytes + source_bytes[best_node.end_byte:]

                    with open(file_path_str, 'wb') as f:
                        f.write(updated_bytes)
                    return self.result(True)
            except Exception as e:
                core.log("coder", f"Tree-sitter edit failed: {e}")

        # 2. Fallback to line-based replacement
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("line number out of range", False)

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            new_lines = new_content.splitlines(keepends=True)
            if not new_lines:
                new_lines = [""]

            lines[start_idx:end_idx] = new_lines

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return self.result(True)

        except Exception as e:
            return self.result(f"error: {e}", False)

    def _find_symbol_end_line(self, lines, start_idx, body_type):
        """Helper to find the end line of a symbol given its start line."""
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
            return end_idx
        else:
            brace_found = False
            start_brace_idx = -1
            for i in range(start_idx, len(lines)):
                if '{' in lines[i]:
                    start_brace_idx = i
                    brace_found = True
                    break

            if not brace_found:
                return start_idx + 1

            brace_count = 0
            for i in range(start_brace_idx, len(lines)):
                line = lines[i]
                brace_count += line.count('{')
                brace_count -= line.count('}')
                if brace_count <= 0:
                    return i + 1
            return len(lines)

    async def add_symbol_before(self, project_name: str, file_path: list, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """
        Inserts a new symbol before the target symbol.

        IMPORTANT: The `content_body` parameter should be raw source code with actual
        newlines and quotes, NOT a JSON-encoded string literal.

        Args:
            target_symbol_name: The name of the symbol to insert before.
            name: The name of the new symbol (for reference, may not be used if content_body contains definition).
            content_body: The complete source code for the new symbol.
        """
        if not self.config.get("allow_function_adding"):
            return self.result("Symbol adding is disabled.", False)

        # Validate content
        is_valid, cleaned_content, error = self._validate_content(content_body, "content_body")
        if not is_valid and error:
            return self.result(f"Content validation error: {error}", False)
        content_body = cleaned_content

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result(f"symbol '{target_symbol_name}' not found", False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            target_line = lines[line_number - 1]
            indent_len = len(target_line) - len(target_line.lstrip())
            indent_str = " " * indent_len

            # Determine if this is inside a class (method)
            is_method = "." in target_symbol_name

            body_lines = content_body.splitlines(keepends=True)
            if is_method:
                # Indent all lines for method context
                new_symbol = "".join(f"{indent_str}{line.lstrip()}" for line in body_lines)
            else:
                new_symbol = content_body

            if not new_symbol.endswith('\n'):
                new_symbol += '\n'
            new_symbol += '\n'

            lines.insert(line_number - 1, new_symbol)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return self.result(True)

        except Exception as e:
            core.log("coder", f"Error in add_symbol_before: {e}")
            return self.result(f"error: {e}", False)

    async def add_symbol_after(self, project_name: str, file_path: list, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """
        Inserts a new symbol after the target symbol.

        IMPORTANT: The `content_body` parameter should be raw source code with actual
        newlines and quotes, NOT a JSON-encoded string literal.

        Args:
            target_symbol_name: The name of the symbol to insert after.
            name: The name of the new symbol (for reference).
            content_body: The complete source code for the new symbol.
        """
        if not self.config.get("allow_function_adding"):
            return self.result("Symbol adding is disabled.", False)

        # Validate content
        is_valid, cleaned_content, error = self._validate_content(content_body, "content_body")
        if not is_valid and error:
            return self.result(f"Content validation error: {error}", False)
        content_body = cleaned_content

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result(f"symbol '{target_symbol_name}' not found", False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            target_line = lines[line_number - 1]
            indent_len = len(target_line) - len(target_line.lstrip())
            indent_str = " " * indent_len

            is_method = "." in target_symbol_name

            body_lines = content_body.splitlines(keepends=True)
            if is_method:
                new_symbol = "".join(f"{indent_str}{line.lstrip()}" for line in body_lines)
            else:
                new_symbol = content_body

            if not new_symbol.endswith('\n'):
                new_symbol += '\n'
            new_symbol += '\n'

            lines.insert(end_idx, new_symbol)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return self.result(True)

        except Exception as e:
            core.log("coder", f"Error in add_symbol_after: {e}")
            return self.result(f"error: {e}", False)

    async def delete_symbol(self, project_name: str, file_path: list, symbol_name: str, language: str = None):
        """
        Deletes a symbol from a file.

        Args:
            symbol_name: Name of the symbol to delete (e.g., "MyClass.old_method")
        """
        if not self.config.get("allow_function_deleting"):
            return self.result("Symbol deletion is disabled.", False)

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist", False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"symbol '{symbol_name}' not found", False)

        # 1. Try Tree-sitter for precise removal
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                parser = Parser(LANGUAGE_MAP[language])
                with open(file_path_str, 'rb') as f:
                    source_bytes = f.read()

                tree = parser.parse(source_bytes)
                target_row = line_number - 1

                candidate_nodes = []
                def find_nodes(node):
                    if node.start_point[0] <= target_row <= node.end_point[0]:
                        lang_config = self.LANGUAGES.get(language, {})
                        if node.type in lang_config.get('symbol_types', {}):
                            candidate_nodes.append(node)
                    for child in node.children:
                        find_nodes(child)

                find_nodes(tree.root_node)

                if candidate_nodes:
                    best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
                    updated_bytes = source_bytes[:best_node.start_byte] + source_bytes[best_node.end_byte:]

                    with open(file_path_str, 'wb') as f:
                        f.write(updated_bytes)
                    return self.result(True)
            except Exception as e:
                core.log("coder", f"Tree-sitter delete failed: {e}")

        # 2. Fallback to line-based removal
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("line number out of range", False)

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            del lines[start_idx:end_idx]

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return self.result(True)

        except Exception as e:
            return self.result(f"error: {e}", False)

    async def search(self, project_name: str, file_path: list, query: str, context_lines: int = 5, max_matches: int = 10, use_regex: bool = False):
        """
        Search for text or regex pattern within a file.
        Returns snippets with line numbers and surrounding context.

        Args:
            query: Search string or regex pattern.
            context_lines: Number of lines to show before/after each match.
            max_matches: Maximum number of matches to return.
            use_regex: If True, treat query as a regex pattern.
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("file does not exist!", False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
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
