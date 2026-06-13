import core
import os
import re
import asyncio
import importlib
import glob as glob_module
import time
import shutil
import stat
from typing import Dict, Any, Optional, Tuple

# --- Tree-sitter Setup ---
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


class Coder(core.module.Module):
    """Allows your AI to write, edit and test code for you."""

    dependencies = [
        "tree-sitter",
        "tree-sitter-python",
        "tree-sitter-javascript",
        "tree-sitter-typescript",
        "tree-sitter-html",
        "tree-sitter-css",
        "tree-sitter-cpp",
        "tree-sitter-c-sharp",
        "tree-sitter-rust",
        "tree-sitter-ruby",
        "tree-sitter-go",
        "tree-sitter-java"
    ]

    # Language-specific formatting tools
    FORMATTERS = {
        'python': ['black', 'autopep8', 'yapf'],
        'javascript': ['prettier', 'eslint'],
        'typescript': ['prettier', 'eslint'],
        'html': ['prettier'],
        'css': ['prettier', 'css-beautify'],
        'ruby': ['rubocop', 'rufo'],
        'go': ['gofmt', 'goimports'],
        'rust': ['rustfmt'],
        'java': ['google-java-format'],
        'c-sharp': ['csharpier'],
        'cpp': ['clang-format'],
    }

    # Language configuration with syntax patterns and metadata
    LANGUAGES = {
        'python': {
            'extensions': ['.py'],
            'body_type': 'indentation',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            ],
            'symbol_types': {
                'class_definition': 'class',
                'function_definition': 'function',
            }
        },
        'javascript': {
            'extensions': ['.js', '.jsx'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'function_declaration': 'function',
                'method_definition': 'method',
                'arrow_function': 'function',
            }
        },
        'typescript': {
            'extensions': ['.ts', '.tsx'],
            'body_type': 'brace',
            'outline_patterns': [
                (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
                (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
                (r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*\([^)]*\)\s*=>', 'function'),
            ],
            'symbol_types': {
                'class_declaration': 'class',
                'function_declaration': 'function',
                'method_definition': 'method',
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

    settings = {
        "sandbox_folder": {
            "default": "~/coder",
            "description": "The folder where all your projects are stored. The AI can only access files within this sandbox."
        },
        "reading_mode": {
            "default": "symbols",
            "type": "select",
            "options": {
                "none": "Prevent reading any files",
                "symbols": "The AI will target specific 'symbols' (functions/class methods) to read their code. Uses treesitter for symbol targeting and syntax error detection.",
                "files": "The AI will read entire files, with a line and filesize limit",
                "both": "The AI will be able to read using symbol tools and full file reading tools"
            }
        },
        "writing_mode": {
            "default": "symbols",
            "type": "select",
            "options": {
                "read-only": "The AI will only be able to read your files, not write to them.",
                "symbols": "The AI will edit code by targeting specific 'symbols' (functions/class methods)",
                "full edits": "The AI will edit code by performing direct file edits and search/replace",
                "both": "The AI will be able to edit using symbol tools and full file editing tools"
            }
        },
        "allow_total_overwrites": {
            "description": "Whether to allow the AI to fully overwrite files when writing mode is set to *full edits* or *both*. This is dangerous with some AI models because they can easily mess up your entire file, but is also sometimes needed for things like refactors.",
            "default": False
        },
        "coding_style": {
            "default": "",
            "description": "Use this to specify style guidelines for your AI to use while coding. Gets added to the system prompt, above the project list.",
            "type": "long_text"
        },
        "add_project_list_to_system_prompt": {
            "default": True,
            "description": "Make your AI aware of all the folders in your sandbox folder, so you can simply say 'in my cute_website project, edit the buttons to be cuter"
        },
        "limits": {
            "folder_blacklist": {
                "description": "Skip these folders when listing projects recursively. Helps not flood your context with hundreds of files, such as with python's `venv` and `__pycache__`)",
                "default": ["venv", "__pycache__"]
            },
            "max_file_size": {
                "description": "Max file size (in MB) the coder should be able to read in one go",
                "default": 10
            },
            "max_read_lines": {
                "description": "Max amount of lines to read from any given file. Use this to prevent your context window from getting stuffed to the brim really fast!",
                "default": 1000
            },
            "max_grep_results": 50,
            "backup_retention_count": {
                "description": "How many backups of each file to keep",
                "default": 10
            }
        },
        "allow_code_execution": {
            "description": "Whether to allow the AI to execute the code it has written. **EXTREMELY DANGEROUS**! It's recommended to use the `sandboxed shell` module instead, point it at your coder sandbox folder.",
            "unsafe": True,
            "default": False
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parser_cache = {}
        self.enabled_tools = []
        self.sandbox_path = os.path.expanduser(
            str(self.config.get("sandbox_folder", default="~/sandbox"))
        ).rstrip(os.path.sep)

        if HAS_TREE_SITTER:
            if not loaded_languages:
                core.log("coder", "Tree-sitter installed but NO language parsers found.")
            else:
                core.log("coder", f"Tree-sitter ENABLED. Languages: {loaded_languages}")
        else:
            core.log("coder", f"Tree-sitter DISABLED. Reason: {disabled_reason}")

        # Core tools always available
        self.enabled_tools.extend([
            "list_full_project_tree",
            "list_project_folder"
        ])

        # Tool sets for different modes
        symbol_reading_tools = ["get_outline", "get_symbol", "format_file"]
        symbol_writing_tools = [
            "create_project", "create_file", "edit_symbol",
            "add_symbol_before", "add_symbol_after", "delete_symbol"
        ]
        file_reading_tools = [
            "read_file", "search_in_file", "grep", "find_files", "format_file"
        ]
        file_writing_tools = [
            "create_project", "create_file", "append_to_file",
            "edit", "search_replace", "format_file"
        ]

        # Reading mode
        match self.config.get("reading_mode"):
            case "symbols":
                self.enabled_tools.extend(symbol_reading_tools)
            case "files":
                self.enabled_tools.extend(file_reading_tools)
            case "both":
                self.enabled_tools.extend(symbol_reading_tools)
                self.enabled_tools.extend(file_reading_tools)

        # Writing mode
        if self.config.get("writing_mode") != "read-only":
            self.enabled_tools.extend(["list_backups", "restore_backup"])

        match self.config.get("writing_mode"):
            case "symbols":
                self.enabled_tools.extend(symbol_writing_tools)
            case "full edits":
                self.enabled_tools.extend(file_writing_tools)
            case "both":
                self.enabled_tools.extend(symbol_writing_tools)
                self.enabled_tools.extend(file_writing_tools)

        if self.config.get("writing_mode") in ("full edits", "both") and self.config.get("allow_total_overwrites"):
            self.enabled_tools.append("overwrite_file")

        if self.config.get("allow_code_execution"):
            self.enabled_tools.append("execute")

        # Disable tools not in enabled list
        for prop_name in dir(self):
            if prop_name.startswith("_") or prop_name.startswith("on_"):
                continue

            attr = getattr(self, prop_name)
            if callable(attr) and prop_name not in self.enabled_tools:
                self.disabled_tools.append(prop_name)

    # ==================== Path Helpers ====================

    def _get_project_path(self, project_name: str) -> str:
        """Resolve project folder path within sandbox."""
        return core.sandbox_path(self.sandbox_path, project_name.strip(os.path.sep))

    def _get_file_path(self, project_name: str, file_path: str) -> str:
        """Resolve file path within a project. File path should be a single string like 'src/main.py'."""
        combined = os.path.join(project_name, file_path.strip(os.path.sep))
        return core.sandbox_path(self.sandbox_path, combined)

    # ==================== File Size Check ====================

    def _check_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Check if file size is within configured limits."""
        max_size_bytes = self.config.get("limits", {}).get("max_file_size", 10) * 1024 * 1024
        try:
            size = os.path.getsize(file_path)
            if size > max_size_bytes:
                return False, f"File size ({size / (1024*1024):.1f}MB) exceeds limit ({max_size_bytes // (1024*1024)}MB)"
            return True, None
        except OSError:
            return True, None

    # ==================== Tree-sitter Helpers ====================

    def _get_parser(self, language: str):
        """Get or create a cached parser for the given language."""
        if language not in self._parser_cache:
            if language in LANGUAGE_MAP:
                self._parser_cache[language] = Parser(LANGUAGE_MAP[language])
        return self._parser_cache.get(language)

    def _parse_file(self, file_path: str, language: str) -> Optional[Tuple[Any, bytes]]:
        """Parse a file using tree-sitter. Returns (tree, source_bytes) or None on failure."""
        parser = self._get_parser(language)
        if parser is None:
            return None

        try:
            with open(file_path, 'rb') as f:
                source_bytes = f.read()
            tree = parser.parse(source_bytes)
            return tree, source_bytes
        except Exception as e:
            core.log("coder", f"Tree-sitter parse failed: {e}")
            return None

    def _verify_syntax(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Verify file has no syntax errors using tree-sitter. Returns (is_valid, error_message)."""
        if not HAS_TREE_SITTER:
            return True, None

        lang = self._get_language_from_ext(file_path)
        if lang not in LANGUAGE_MAP:
            return True, None

        try:
            result = self._parse_file(file_path, lang)
            if result is None:
                return True, None
            tree, source_bytes = result

            if tree.root_node.has_error:
                # HTML special handling for bare ampersands
                if lang == 'html':
                    error_nodes = []
                    def _collect_errors(node):
                        if node.type == 'ERROR':
                            error_nodes.append(node)
                        for child in node.children:
                            _collect_errors(child)
                    _collect_errors(tree.root_node)

                    if error_nodes:
                        all_ampersand_issues = all(
                            '&' in source_bytes[e.start_byte:e.end_byte].decode('utf-8', errors='replace').strip()
                            and '<' not in source_bytes[e.start_byte:e.end_byte].decode('utf-8', errors='replace')
                            and '>' not in source_bytes[e.start_byte:e.end_byte].decode('utf-8', errors='replace')
                            for e in error_nodes
                        )
                        if all_ampersand_issues:
                            return True, None

                error_msg = self._first_error_message(tree.root_node, source_bytes, os.path.basename(file_path))
                if error_msg:
                    return False, error_msg

                # Fallback error location
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
                    return False, f"Syntax error at line {line}, column {col}"
                return False, "Syntax error detected"

            return True, None
        except Exception as e:
            core.log("coder", f"Syntax verification skipped: {e}")
            return True, None

    def _verify_syntax_content(self, content: bytes, language: str) -> Tuple[bool, Optional[str]]:
        """Verify content has no syntax errors using tree-sitter without writing to disk. Returns (is_valid, error_message)."""
        if not HAS_TREE_SITTER:
            return True, None

        if language not in LANGUAGE_MAP:
            return True, None

        try:
            parser = self._get_parser(language)
            if parser is None:
                return True, None

            tree = parser.parse(content)

            if tree.root_node.has_error:
                # HTML special handling for bare ampersands
                if language == 'html':
                    error_nodes = []
                    def _collect_errors(node):
                        if node.type == 'ERROR':
                            error_nodes.append(node)
                        for child in node.children:
                            _collect_errors(child)
                    _collect_errors(tree.root_node)

                    if error_nodes:
                        all_ampersand_issues = all(
                            '&' in content[e.start_byte:e.end_byte].decode('utf-8', errors='replace').strip()
                            and '<' not in content[e.start_byte:e.end_byte].decode('utf-8', errors='replace')
                            and '>' not in content[e.start_byte:e.end_byte].decode('utf-8', errors='replace')
                            for e in error_nodes
                        )
                        if all_ampersand_issues:
                            return True, None

                error_msg = self._first_error_message(tree.root_node, content, "content")
                if error_msg:
                    return False, error_msg

                # Fallback error location
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
                    return False, f"Syntax error at line {line}, column {col}"
                return False, "Syntax error detected"

            return True, None
        except Exception as e:
            core.log("coder", f"Syntax verification skipped: {e}")
            return True, None

    def _first_error_message(self, node, source_bytes: bytes, file_name: str = "file") -> Optional[str]:
        """Walk the tree to find first ERROR/MISSING node and produce detailed message."""
        # Check children first (depth-first)
        for child in node.children:
            msg = self._first_error_message(child, source_bytes, file_name)
            if msg:
                return msg

        if node.type not in ('ERROR', 'MISSING'):
            return None

        start_line = node.start_point[0] + 1
        start_col = node.start_point[1] + 1
        snippet = source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace').strip()

        lines = source_bytes.decode('utf-8', errors='replace').split('\n')

        # Build context
        context_lines = []
        context_radius = 2
        for i in range(max(0, start_line - 1 - context_radius), start_line - 1):
            context_lines.append(f"    {i+1:4d}: {lines[i]}")
        context_lines.append(f"  >> {start_line:4d}: {lines[start_line - 1]}")
        for i in range(start_line, min(len(lines), start_line + context_radius)):
            context_lines.append(f"    {i+1:4d}: {lines[i]}")

        error_desc = self._describe_error(node, snippet, lines, start_line)

        msg_lines = [f"Syntax error in {file_name}:"]
        msg_lines.append(f"  {error_desc}")
        msg_lines.append(f"  At line {start_line}, column {start_col}")
        if snippet:
            display_snippet = snippet[:80] + "..." if len(snippet) > 80 else snippet
            msg_lines.append(f"  Problematic code: {display_snippet!r}")
        msg_lines.extend(context_lines)

        return "\n".join(msg_lines)

    def _describe_error(self, node, snippet: str, lines: list, line_num: int) -> str:
        """Provide human-readable error description."""
        if node.type == 'MISSING':
            return self._describe_missing_token(node, lines, line_num)
        return self._describe_error_token(node, snippet, lines, line_num)

    def _describe_missing_token(self, node, lines: list, line_num: int) -> str:
        """Describe what token or structure is missing."""
        prev_line = lines[line_num - 2] if line_num > 1 else ""
        curr_line = lines[line_num - 1] if line_num <= len(lines) else ""
        next_line = lines[line_num] if line_num < len(lines) else ""

        # Common missing token patterns
        for open_char, close_char in [('(', ')'), ('[', ']'), ('{', '}')]:
            if curr_line.rstrip().endswith(open_char) and not next_line.strip().startswith(close_char):
                return f"Missing closing '{close_char}'"

        # Unterminated string
        for quote in ("'", '"'):
            if curr_line.rstrip().count(quote) % 2 == 1:
                return f"Unterminated string (missing {quote})"

        # Missing colon after keyword
        for kw in ('def', 'class', 'if', 'else', 'elif', 'for', 'while', 'try', 'except', 'finally', 'with'):
            if curr_line.strip().startswith(kw) and not curr_line.rstrip().endswith(':'):
                return f"Missing ':' after '{kw}'"

        # Missing expression after statement
        for kw in ('return', 'raise', 'yield'):
            if curr_line.strip().startswith(kw) and curr_line.strip() == kw:
                return f"Missing expression after '{kw}'"

        if prev_line.rstrip().endswith(':') and not next_line.strip():
            return "Missing indented block after ':'"

        return f"Missing expected token at line {line_num}"

    def _describe_error_token(self, node, snippet: str, lines: list, line_num: int) -> str:
        """Describe unexpected syntax found."""
        if not snippet:
            return f"Unexpected empty syntax at line {line_num}"

        stripped = snippet.strip()

        # Mismatched delimiters
        if stripped in ('(', ')', '[', ']', '{', '}'):
            matching = {'(': ')', ')': '(', '[': ']', ']': '[', '{': '}', '}': '{'}
            return f"Unexpected '{stripped}' (expected '{matching[stripped]}')"

        # Unterminated strings
        for quote in ("'", '"'):
            if stripped.startswith(quote) and not stripped.endswith(quote):
                return f"Unterminated string starting with {quote}"

        # Unexpected operators
        if stripped in ('==', '!=', '<=', '>=') and line_num <= len(lines):
            prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
            if not prev.endswith(('(', '[', ',', '=', ':')):
                return f"Unexpected '{stripped}' (use '=' for assignment)"

        if len(stripped) > 40:
            stripped = stripped[:40] + "..."
        return f"Unexpected syntax: '{stripped}' at line {line_num}"

    # ==================== Language Detection ====================

    def _get_language_from_ext(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = os.path.splitext(file_path)[1].lower()
        for lang, config in self.LANGUAGES.items():
            if ext in config.get('extensions', []):
                return lang
        return 'generic'

    def _detect_language_from_content(self, content: str) -> Optional[str]:
        """Detect language from shebang or magic comments."""
        first_lines = content[:2048].split('\n')
        for line in first_lines:
            line = line.strip()
            if line.startswith('#!'):
                if 'python' in line:
                    return 'python'
                elif 'ruby' in line:
                    return 'ruby'
                elif 'bash' in line or 'sh' in line:
                    return 'bash'
            if '// @ts-check' in line:
                return 'typescript'
            if '<?php' in line:
                return 'php'
        return None

    def _detect_language(self, file_path: str, content: str = None) -> str:
        """Detect language from extension, falling back to content analysis."""
        lang = self._get_language_from_ext(file_path)
        if lang != 'generic' and lang in LANGUAGE_MAP:
            return lang
        if content:
            detected = self._detect_language_from_content(content)
            if detected and detected in self.LANGUAGES:
                return detected
        return lang

    # ==================== Backup System ====================

    def _get_backup_dir(self) -> str:
        """Get or create the backup directory."""
        backup_dir = core.sandbox_path(self.sandbox_path, ".backups")
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    async def _backup_file(self, file_path: str) -> Optional[str]:
        """Create timestamped backup. Returns backup path or None on failure."""
        if not os.path.exists(file_path):
            return None

        try:
            backup_dir = self._get_backup_dir()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(file_path)
            backup_name = f"{basename}.{timestamp}.bak"
            backup_path = os.path.join(backup_dir, backup_name)
            shutil.copy2(file_path, backup_path)
            self._cleanup_old_backups(basename)
            return backup_path
        except Exception as e:
            core.log("coder", f"Backup failed: {e}")
            return None

    def _cleanup_old_backups(self, basename: str, max_count: int = None):
        """Remove old backups beyond retention limit."""
        max_count = max_count or self.config.get("limits", {}).get("backup_retention_count", 10)
        backup_dir = self._get_backup_dir()
        try:
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith(basename + ".") and f.endswith(".bak"):
                    full_path = os.path.join(backup_dir, f)
                    backups.append((os.path.getmtime(full_path), full_path))

            backups.sort(reverse=True)
            for _, path in backups[max_count:]:
                try:
                    os.remove(path)
                except OSError:
                    pass
        except Exception as e:
            core.log("coder", f"Backup cleanup failed: {e}")

    # ==================== Symbol Helpers ====================

    def _walk_for_symbols(self, node, language: str, symbols: list, prefix: str = ""):
        """Recursively walk tree-sitter nodes to find symbols."""
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
                # Recurse into nested definitions
                for child in node.children:
                    self._walk_for_symbols(child, language, symbols, prefix=f"{full_name}.")
                return

        for child in node.children:
            self._walk_for_symbols(child, language, symbols, prefix=prefix)

    def _find_symbol_info(self, file_path: str, symbol_name: str, language: str) -> Optional[Tuple[Optional[Any], int]]:
        """Find symbol by name. Returns (node, line_number) or None."""
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                result = self._parse_file(file_path, language)
                if result is None:
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
                    return (target_node, target_node.start_point[0] + 1)
            except Exception:
                pass

        # Fallback to regex
        parts = symbol_name.split('.')
        last_part = parts[-1]
        lang_config = self.LANGUAGES.get(language, {})
        patterns = lang_config.get('outline_patterns', [
            (r'^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'class'),
            (r'^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
            (r'^\s*function\s+([a-zA-Z_][a-zA-Z0-9_]*)', 'function'),
        ])

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for idx, line in enumerate(f):
                    for pattern, sym_type in patterns:
                        match = re.search(pattern, line)
                        if match and match.group(1) == last_part:
                            return (None, idx + 1)
        except Exception:
            pass

        return None

    def _find_symbol_line(self, file_path: str, symbol_name: str, language: str) -> Optional[int]:
        """Find line number of a symbol."""
        info = self._find_symbol_info(file_path, symbol_name, language)
        return info[1] if info else None

    def _find_symbol_end_line(self, lines: list, start_idx: int, body_type: str) -> int:
        """Find end line of a symbol given its start line."""
        if body_type == 'indentation':
            def get_indent(l):
                return len(l) - len(l.lstrip())
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
            # Brace-based: handle braces inside strings and comments
            brace_count = 0
            in_string = None
            in_line_comment = False
            in_block_comment = False
            start_brace_idx = -1

            for i in range(start_idx, len(lines)):
                line = lines[i]
                j = 0
                while j < len(line):
                    char = line[j]

                    if in_block_comment:
                        if char == '*' and j + 1 < len(line) and line[j + 1] == '/':
                            in_block_comment = False
                            j += 2
                            continue
                        j += 1
                        continue

                    if in_line_comment:
                        if char == '\n':
                            in_line_comment = False
                        j += 1
                        continue

                    if in_string:
                        if char == '\\' and j + 1 < len(line):
                            j += 2
                            continue
                        if char == in_string:
                            in_string = None
                        j += 1
                        continue

                    if char in ('"', "'", '`'):
                        in_string = char
                        j += 1
                        continue
                    if char == '/' and j + 1 < len(line) and line[j + 1] == '/':
                        in_line_comment = True
                        j += 1
                        continue
                    if char == '/' and j + 1 < len(line) and line[j + 1] == '*':
                        in_block_comment = True
                        j += 2
                        continue

                    if char == '{':
                        if start_brace_idx == -1:
                            start_brace_idx = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count <= 0:
                            return i + 1

                    j += 1

            if start_brace_idx == -1:
                return start_idx + 1
            return len(lines)

    def _get_symbol_nodes(self, file_path: str, symbol_name: str, language: str):
        """Get candidate tree-sitter nodes for a symbol."""
        if not (HAS_TREE_SITTER and language in LANGUAGE_MAP):
            return []

        result = self._parse_file(file_path, language)
        if result is None:
            return []

        tree, source_bytes = result
        line_number = self._find_symbol_line(file_path, symbol_name, language)
        if not line_number:
            return []

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

        if not candidate_nodes:
            return []

        best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
        return [(best_node, source_bytes)]

    # ==================== Project Navigation ====================

    async def list_full_project_tree(self, project_name: str, depth_limit: int = 5, max_files_per_folder: int = 50):
        """Get a complete recursive tree view of a project structure.

        Use this FIRST to understand the overall project layout before reading specific files.
        Helps you navigate large codebases by showing the directory structure.

        Args:
            project_name: Name of the project folder
            depth_limit: Maximum recursion depth (default: 5)
            max_files_per_folder: Maximum files to show per folder (default: 50)

        Returns:
            Nested dictionary representing folder structure, or error message
        """
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
                        if current_depth < depth_limit:
                            tree[folder_key] = _build_tree(entry.path, current_depth + 1)
                        else:
                            tree[folder_key] = {}
            except OSError:
                pass
            return tree

        try:
            tree = _build_tree(project_path, 0)
            return self.result(tree, success=True)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    async def list_project_folder(self, project_name: str, sub_path: str = ""):
        """List immediate contents of a folder within a project.

        Non-recursive listing. Use this to explore specific directories.

        Args:
            project_name: Name of the project
            sub_path: Relative path within project (e.g., 'src/components'). Use '' for root.

        Returns:
            Dictionary with 'contents' key listing files and folders, or error message
        """
        target_path = self._get_project_path(project_name)
        if sub_path:
            target_path = core.sandbox_path(target_path, sub_path)

        if not os.path.exists(target_path):
            return self.result("Error: path does not exist", success=False)
        if not os.path.isdir(target_path):
            return self.result("Error: path is not a directory", success=False)

        try:
            return self.result({"contents": os.listdir(target_path)}, success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== File Creation ====================

    async def create_project(self, project_name: str):
        """Create a new project folder.

        Use this to start a new project. The folder will be created in the sandbox.

        Args:
            project_name: Name for the new project folder

        Returns:
            Success message or error if project already exists
        """
        if self.config.get("writing_mode") == "read-only":
            return self.result("Error: Coder is in read-only mode", success=False)

        base_path = self._get_project_path(project_name)

        if os.path.exists(base_path):
            return self.result("Project already exists! Choose a different name.", False)

        try:
            os.makedirs(base_path, exist_ok=True)
            return self.result(f"Project '{project_name}' created.", success=True)
        except OSError as e:
            return self.result(f"Error creating project: {e}", success=False)

    async def create_file(self, project_name: str, file_path: str, content: str):
        """Create a new file with specified content.

        Cannot overwrite existing files. Creates parent directories automatically.
        Validates syntax before saving.

        Args:
            project_name: Name of the project
            file_path: Relative path for the new file (e.g., 'src/utils/helpers.py')
            content: Initial file content

        Returns:
            Success message or error (syntax errors will prevent file creation)
        """
        file_path_str = self._get_file_path(project_name, file_path)

        if os.path.exists(file_path_str):
            return self.result("Error: File already exists. Use edit tools to modify existing files.", success=False)

        # Check syntax BEFORE writing to disk
        language = self._get_language_from_ext(file_path_str)
        content_bytes = content.encode('utf-8')
        is_valid, error = self._verify_syntax_content(content_bytes, language)
        if not is_valid:
            return self.result(f"Error: {error}. File not written due to syntax errors. Fix and try again.", success=False)

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)

            return self.result(f"File created: {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== File Reading ====================

    async def read_file(self, project_name: str, file_path: str, limit: int = None, offset: int = None):
        """Read entire file content with pagination support.

        For large files, use offset and limit to read in chunks.
        File mode tool - prefer get_symbol for reading specific functions/classes.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            limit: Maximum lines to read (default: uses max_read_lines config)
            offset: Starting line number (1-indexed)

        Returns:
            File content as string, possibly truncated with continuation info
        """
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

            start_idx = 0
            if offset is not None:
                start_idx = max(0, min(offset - 1, total_lines))

            end_idx = total_lines
            if limit is not None:
                end_idx = min(start_idx + limit, total_lines)

            line_limit_reached = False
            if (end_idx - start_idx) > max_lines:
                end_idx = start_idx + max_lines
                line_limit_reached = True

            selected_lines = lines[start_idx:end_idx]
            result = "".join(selected_lines)

            size_limit_reached = False
            max_bytes = self.config.get("limits", {}).get("max_file_size", 10) * 1024 * 1024
            if len(result.encode('utf-8')) > max_bytes:
                while len(result.encode('utf-8')) > max_bytes and result:
                    result = result[:-1]
                size_limit_reached = True

            if offset and not result:
                return self.result("Offset beyond file end. Use a lower offset.", success=False)

            response = result
            if end_idx < total_lines:
                reason = "line limit reached" if line_limit_reached else "limit reached"
                remaining = total_lines - end_idx
                next_offset = end_idx + 1
                response += f"\n[Output truncated - {reason}. {remaining} lines remain, starting from line {next_offset}]"

            if size_limit_reached:
                response += "\n[Output truncated - file size limit reached]"

            return response
        except OSError as e:
            return self.result(f"Error reading file: {e}", success=False)

    async def overwrite_file(self, project_name: str, file_path: str, content: str):
        """Completely replace a file's content.

        DANGEROUS: Destroys existing content. Creates backup automatically.
        Only available when allow_total_overwrites is enabled.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            content: New complete file content

        Returns:
            Success message or error
        """
        file_path_str = self._get_file_path(project_name, file_path)

        # Check syntax BEFORE writing to disk
        language = self._get_language_from_ext(file_path_str)
        content_bytes = content.encode('utf-8')
        is_valid, error = self._verify_syntax_content(content_bytes, language)
        if not is_valid:
            return self.result(f"Error: {error}. File not overwritten due to syntax errors. Fix and try again.", success=False)

        await self._backup_file(file_path_str)

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)

            return self.result(f"File overwritten: {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def append_to_file(self, project_name: str, file_path: str, content: str):
        """Append content to end of file.

        Creates file if it doesn't exist. Adds newline before content if needed.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            content: Content to append

        Returns:
            Success message or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        mode = 'a' if os.path.exists(file_path_str) else 'w'

        # Build the combined content to check syntax BEFORE writing
        if mode == 'a' and os.path.exists(file_path_str):
            with open(file_path_str, 'r', encoding='utf-8') as f:
                existing_content = f.read()
            if existing_content and not existing_content.endswith('\n'):
                combined_content = existing_content + '\n' + content
            else:
                combined_content = existing_content + content
        else:
            combined_content = content

        # Ensure trailing newline
        if not combined_content.endswith('\n'):
            combined_content += '\n'

        # Check syntax BEFORE writing to disk
        language = self._get_language_from_ext(file_path_str)
        combined_bytes = combined_content.encode('utf-8')
        is_valid, error = self._verify_syntax_content(combined_bytes, language)
        if not is_valid:
            return self.result(f"Error: {error}. Content not appended due to syntax errors. Fix and try again.", success=False)

        try:
            with open(file_path_str, mode, encoding='utf-8') as f:
                if mode == 'a' and os.path.getsize(file_path_str) > 0:
                    f.write('\n')
                f.write(content)
                if not content.endswith('\n'):
                    f.write('\n')

            return self.result(f"Content appended to {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== Code Execution ====================

    async def execute(self, project_name: str, file_path: str, timeout: int = 30):
        """Execute a script file.

        DANGEROUS: Runs arbitrary code. Only available when allow_code_execution is enabled.
        Consider using the sandboxed_shell module instead.

        Args:
            project_name: Name of the project
            file_path: Relative path to executable script
            timeout: Maximum execution time in seconds (default: 30)

        Returns:
            Dictionary with stdout, stderr, and returncode, or error message
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

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
                    return self.result(f"Error (exit code {proc.returncode}): {error_msg}", success=False)

                return self.result({"stdout": stdout_str, "stderr": stderr_str, "returncode": proc.returncode}, success=True)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except:
                    pass
                return self.result(f"Error: Execution timed out after {timeout} seconds", success=False)
        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== Symbol-Based Operations ====================

    async def get_outline(self, project_name: str, file_path: str, language: str = None):
        """List all symbols (classes, functions, methods) in a file.

        USE THIS FIRST to understand file structure before reading specific symbols.
        Essential for navigating unfamiliar code - shows you what's available to work with.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            language: Optional language hint (auto-detected from extension)

        Returns:
            Dictionary with 'symbols' list containing {name, type} dicts, or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # Try tree-sitter first
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                result = self._parse_file(file_path_str, language)
                if result is not None:
                    tree, source_bytes = result
                    symbols = []
                    self._walk_for_symbols(tree.root_node, language, symbols)
                    symbols.sort(key=lambda x: x['line'])
                    return self.result({"symbols": [{"name": s["name"], "type": s["type"]} for s in symbols]}, success=True)
            except Exception as e:
                core.log("coder", f"Tree-sitter failed, falling back to regex: {e}")

        # Fallback to regex
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
            return self.result({"symbols": outline}, success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def get_symbol(self, project_name: str, file_path: str, symbol_name: str, language: str = None):
        """Read a specific function, class, or method by name.

        THE PREFERRED WAY TO READ CODE. Use after get_outline to find symbol names.
        Precisely extracts just the code you need without reading entire files.

        For nested symbols, use dot notation (e.g., 'ClassName.method_name').

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            symbol_name: Name of symbol to read (use 'Class.method' for methods)
            language: Optional language hint (auto-detected from extension)

        Returns:
            Complete source code of the symbol, or error message
        """
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # Try tree-sitter for precise extraction
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                found_code = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                return found_code

        # Fallback to line-based extraction
        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)

        lang_config = self.LANGUAGES.get(language, {})
        body_type = lang_config.get('body_type', 'brace')

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("Error: line number out of range", success=False)

            start_idx = line_number - 1

            if body_type == 'indentation':
                def get_indent(l):
                    return len(l) - len(l.lstrip())
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
                end_idx = self._find_symbol_end_line(lines, start_idx, body_type)
                body_lines = lines[start_idx:end_idx]

            return "".join(body_lines)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def edit_symbol(self, project_name: str, file_path: str, symbol_name: str, new_content: str, language: str = None):
        """Replace a symbol's implementation with new code.

        The PRIMARY way to edit code. Safer and more precise than file-level edits.
        Automatically backs up before editing. Validates syntax before changes.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            symbol_name: Name of symbol to replace (use 'Class.method' for methods)
            new_content: New implementation code
            language: Optional language hint (auto-detected)

        Returns:
            Success message or error (syntax errors will prevent the edit)
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)

        # Try tree-sitter for precise byte-level replacement
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                new_content_bytes = new_content.encode('utf-8')
                updated_bytes = source_bytes[:node.start_byte] + new_content_bytes + source_bytes[node.end_byte:]

                # Check syntax BEFORE writing to disk
                is_valid, error = self._verify_syntax_content(updated_bytes, language)
                if not is_valid:
                    return self.result(f"Error: {error}. Edit not applied due to syntax errors. Fix and try again.", success=False)

                await self._backup_file(file_path_str)

                with open(file_path_str, 'wb') as f:
                    f.write(updated_bytes)

                return self.result(f"Symbol '{symbol_name}' edited in {file_path}", success=True)

        # Fallback to line-based replacement
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("Error: line number out of range", success=False)

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            new_lines = new_content.splitlines(keepends=True)
            if not new_lines:
                new_lines = [""]

            # Build the new lines list in memory
            new_lines_list = lines[:start_idx] + new_lines + lines[end_idx:]
            combined_content = "".join(new_lines_list)

            # Check syntax BEFORE writing to disk
            combined_bytes = combined_content.encode('utf-8')
            is_valid, error = self._verify_syntax_content(combined_bytes, language)
            if not is_valid:
                return self.result(f"Error: {error}. Edit not applied due to syntax errors. Fix and try again.", success=False)

            await self._backup_file(file_path_str)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(new_lines_list)

            return self.result(f"Symbol '{symbol_name}' edited in {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def add_symbol_before(self, project_name: str, file_path: str, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """Insert a new symbol before an existing symbol.

        Use to add new functions, classes, or methods before the target location.
        Automatically preserves correct indentation for the context.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            target_symbol_name: Name of existing symbol to insert before
            name: Name for the new symbol (for validation)
            content_body: Complete code for the new symbol
            language: Optional language hint (auto-detected)

        Returns:
            Success message or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result(f"Error: symbol '{target_symbol_name}' not found", success=False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

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

            insert_pos = line_number - 1
            if insert_pos > 0 and not lines[insert_pos - 1].endswith('\n'):
                lines.insert(insert_pos, '\n')
                insert_pos += 1

            # Build the new lines list in memory
            new_lines_list = lines[:insert_pos] + [new_symbol] + lines[insert_pos:]
            combined_content = "".join(new_lines_list)

            # Check syntax BEFORE writing to disk
            combined_bytes = combined_content.encode('utf-8')
            is_valid, error = self._verify_syntax_content(combined_bytes, language)
            if not is_valid:
                return self.result(f"Error: {error}. Addition not applied due to syntax errors. Fix and try again.", success=False)

            await self._backup_file(file_path_str)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(new_lines_list)

            return self.result(f"Symbol '{name}' added before '{target_symbol_name}'", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def add_symbol_after(self, project_name: str, file_path: str, target_symbol_name: str, name: str, content_body: str, language: str = None):
        """Insert a new symbol after an existing symbol.

        Use to add new functions, classes, or methods after the target location.
        Automatically preserves correct indentation and placement.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            target_symbol_name: Name of existing symbol to insert after
            name: Name for the new symbol (for validation)
            content_body: Complete code for the new symbol
            language: Optional language hint (auto-detected)

        Returns:
            Success message or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result(f"Error: symbol '{target_symbol_name}' not found", success=False)

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

            if end_idx > 0 and not lines[end_idx - 1].endswith('\n'):
                lines.insert(end_idx, '\n')
                end_idx += 1

            # Build the new lines list in memory
            new_lines_list = lines[:end_idx] + [new_symbol] + lines[end_idx:]
            combined_content = "".join(new_lines_list)

            # Check syntax BEFORE writing to disk
            combined_bytes = combined_content.encode('utf-8')
            is_valid, error = self._verify_syntax_content(combined_bytes, language)
            if not is_valid:
                return self.result(f"Error: {error}. Addition not applied due to syntax errors. Fix and try again.", success=False)

            await self._backup_file(file_path_str)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(new_lines_list)

            return self.result(f"Symbol '{name}' added after '{target_symbol_name}'", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def delete_symbol(self, project_name: str, file_path: str, symbol_name: str, language: str = None):
        """Remove a symbol from a file.

        Deletes the entire function, class, or method. Creates backup first.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            symbol_name: Name of symbol to delete (use 'Class.method' for methods)
            language: Optional language hint (auto-detected)

        Returns:
            Success message or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result(f"Error: symbol '{symbol_name}' not found", success=False)

        # Try tree-sitter for precise removal
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                updated_bytes = source_bytes[:node.start_byte] + source_bytes[node.end_byte:]

                # Check syntax BEFORE writing to disk
                is_valid, error = self._verify_syntax_content(updated_bytes, language)
                if not is_valid:
                    return self.result(f"Error: {error}. Deletion not applied due to syntax errors. Fix and try again.", success=False)

                await self._backup_file(file_path_str)

                with open(file_path_str, 'wb') as f:
                    f.write(updated_bytes)

                return self.result(f"Symbol '{symbol_name}' deleted from {file_path}", success=True)

        # Fallback to line-based removal
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result("Error: line number out of range", success=False)

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            # Build the new lines list in memory
            new_lines_list = lines[:start_idx] + lines[end_idx:]
            combined_content = "".join(new_lines_list)

            # Check syntax BEFORE writing to disk
            combined_bytes = combined_content.encode('utf-8')
            is_valid, error = self._verify_syntax_content(combined_bytes, language)
            if not is_valid:
                return self.result(f"Error: {error}. Deletion not applied due to syntax errors. Fix and try again.", success=False)

            await self._backup_file(file_path_str)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(new_lines_list)

            return self.result(f"Symbol '{symbol_name}' deleted from {file_path}", success=True)
        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== Search Operations ====================

    async def search_in_file(self, project_name: str, file_path: str, query: str, context_lines: int = 5, max_matches: int = 10):
        """Search for text within a single file.

        Returns matching lines with surrounding context. Case-insensitive by default.
        Use this to find specific strings or patterns in a known file.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            query: Text to search for (literal string, NOT regex)
            context_lines: Lines of context above/below each match (default: 5)
            max_matches: Maximum number of matches to return (default: 10)

        Returns:
            Dictionary with match count and formatted results, or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            matches = []
            num_lines = len(lines)
            query_lower = query.lower()

            for i, line in enumerate(lines):
                if len(matches) >= max_matches:
                    break

                if query_lower in line.lower():
                    line_num = i + 1
                    snippet = [f"--- Match at line {line_num} ---"]

                    start_idx = max(0, i - context_lines)
                    end_idx = min(num_lines, i + context_lines + 1)

                    for j in range(start_idx, end_idx):
                        curr_line_num = j + 1
                        curr_line_content = lines[j].rstrip('\n\r')
                        marker = "  <-- MATCH" if curr_line_num == line_num else ""
                        snippet.append(f"{curr_line_num:4}: {curr_line_content}{marker}")

                    matches.append("\n".join(snippet))

            if not matches:
                return self.result({"matches": 0, "file": file_path}, success=True)

            result_str = "\n\n".join(matches)
            return self.result({"matches": len(matches), "file": file_path, "results": result_str}, success=True)

        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def search_replace(self, project_name: str, file_path: str, query: str, replacement: str):
        """Replace all occurrences of a string in a file.

        Literal string replacement (NOT regex). Replaces ALL matches.
        Use for simple text substitutions across entire file.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            query: Text to find (literal string, NOT regex)
            replacement: Text to replace with

        Returns:
            Dictionary with replacement count, or error
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                content = f.read()

            count = content.count(query)
            new_content = content.replace(query, replacement)

            if count > 0:
                # Check syntax BEFORE writing to disk
                language = self._get_language_from_ext(file_path_str)
                new_content_bytes = new_content.encode('utf-8')
                is_valid, error = self._verify_syntax_content(new_content_bytes, language)
                if not is_valid:
                    return self.result(f"Error: {error}. Replacement not applied due to syntax errors. Fix and try again.", success=False)

                await self._backup_file(file_path_str)

                with open(file_path_str, 'w', encoding='utf-8') as f:
                    f.write(new_content)

                return self.result({
                    "success": True,
                    "message": f"Replaced {count} occurrence(s)",
                    "file": file_path,
                                        "replacements": count
                }, success=True)
            else:
                return self.result({"success": True, "message": "No matches found. File unchanged.", "file": file_path}, success=True)

        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def edit(self, project_name: str, file_path: str, old_text: str, new_text: str):
        """Perform a single, precise text replacement in a file.

        Finds the first exact match of `old_text` and replaces it with `new_text`.
        Use this for targeted edits when you know the exact text to change.
        SAFER than search_replace as it only modifies one specific block.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            old_text: Exact text to find (must match exactly, including whitespace)
            new_text: Text to replace it with

        Returns:
            Success message or error if exact text not found
        """
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result("Error: file does not exist", success=False)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                content = f.read()

            if old_text not in content:
                return self.result("Error: old_text not found. The exact text was not found. Ensure it matches exactly including whitespace.", success=False)

            new_content = content.replace(old_text, new_text, 1)

            # Check syntax BEFORE writing to disk
            language = self._get_language_from_ext(file_path_str)
            new_content_bytes = new_content.encode('utf-8')
            is_valid, error = self._verify_syntax_content(new_content_bytes, language)
            if not is_valid:
                return self.result(f"Error: {error}. Edit not applied due to syntax errors. Fix and try again.", success=False)

            await self._backup_file(file_path_str)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.write(new_content)

            return self.result(f"Successfully applied edit to {file_path}", success=True)

        except OSError as e:
            return self.result(f"Error: {e}", success=False)

    async def grep(self, project_name: str, path: str = "", pattern: str = "", case_sensitive: bool = False, max_results: int = None):
        """Search for a text pattern across all files in a project.

        Performs a literal string search (NOT regex) across the entire codebase.
        Use this to find where a function, variable, or string is used across multiple files.

        Args:
            project_name: Name of the project
            path: Optional relative path to limit search scope (e.g., 'src/utils')
            pattern: Text to search for (literal string, NOT regex)
            case_sensitive: Whether to match case (default: False)
            max_results: Maximum results to return (default: uses max_grep_results config)

        Returns:
            Dictionary with pattern, match count, and list of 'file:line: content' results
        """
        search_dir = self._get_project_path(project_name)
        if path:
            search_dir = core.sandbox_path(search_dir, path)

        if not os.path.isdir(search_dir):
            return self.result("Error: search directory does not exist", success=False)

        max_results = max_results or self.config.get("limits", {}).get("max_grep_results", 50)

        try:
            search_text = pattern if case_sensitive else pattern.lower()

            results = []
            file_count = 0
            total_matches = 0

            for root, dirs, files in os.walk(search_dir):
                # Skip hidden and common non-source directories
                skip_dirs = {'venv', '__pycache__', '.git', 'node_modules', '.idea', '.vscode'}
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in skip_dirs]

                for filename in sorted(files):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, search_dir)

                    # Skip binary files by extension
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ('.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.db', '.sqlite', '.png', '.jpg', '.gif', '.pdf'):
                        continue

                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            for line_num, line in enumerate(f, 1):
                                line_search = line if case_sensitive else line.lower()
                                if search_text in line_search:
                                    snippet = line.rstrip('\n')[:200]
                                    results.append(f"{rel_path}:{line_num}: {snippet}")
                                    total_matches += 1
                                    if total_matches >= max_results:
                                        break
                                if total_matches >= max_results:
                                    break
                    except (IOError, OSError):
                        continue

                    file_count += 1
                    if total_matches >= max_results:
                        break

                if total_matches >= max_results:
                    break

            return self.result({
                "pattern": pattern,
                "matches": len(results),
                "files_searched": file_count,
                "truncated": total_matches > max_results,
                "results": results
            }, success=True)

        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    async def find_files(self, project_name: str, pattern: str = "*", path: str = "", file_type: str = "any"):
        """Find files matching a glob pattern within a project.

        Use this to locate files by name or extension (e.g., '*.py', 'test_*.js').
        Faster than grep when you just need to find file paths.

        Args:
            project_name: Name of the project
            pattern: Glob pattern to match (e.g., '**/*.py' for recursive, '*.txt' for current dir)
            path: Optional relative path to limit search scope
            file_type: Filter by 'file', 'directory', or 'any' (default: 'any')

        Returns:
            Dictionary with pattern, count, and sorted list of matching file paths
        """
        search_dir = self._get_project_path(project_name)
        if path:
            search_dir = core.sandbox_path(search_dir, path)

        if not os.path.exists(search_dir):
            return self.result("Error: search directory does not exist", success=False)

        try:
            full_pattern = os.path.join(search_dir, pattern)
            matches = glob_module.glob(full_pattern, recursive=True)

            results = []
            for match in matches:
                rel_path = os.path.relpath(match, search_dir)

                if file_type == "directory" and not os.path.isdir(match):
                    continue
                if file_type == "file" and not os.path.isfile(match):
                    continue

                # Ensure the result is within the sandbox (glob can sometimes escape with symlinks)
                try:
                    core.sandbox_path(search_dir, rel_path)
                    results.append(rel_path)
                except ValueError:
                    # Path escaped sandbox, skip it
                    continue

            return self.result({"pattern": pattern, "count": len(results), "files": sorted(results)}, success=True)

        except Exception as e:
            return self.result(f"Error: {e}", success=False)

    # ==================== Backup Management ====================

    async def list_backups(self, project_name: str, file_path: str) -> dict:
        """List available backups for a file.

        Backups are created automatically before edits. Use this to see restore options.
        Backups are ordered newest to oldest.

        Args:
            project_name: Name of the project
            file_path: Relative path to file

        Returns:
            Dictionary with list of backups (each with index, filename, timestamp)
        """
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
                    mtime = os.path.getmtime(full_path)
                    backups.append({
                        "mtime": mtime,
                        "filename": f,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime))
                    })

            if not backups:
                return {"success": True, "backups": []}

            # Sort by mtime descending (newest first)
            backups.sort(key=lambda x: x["mtime"], reverse=True)

            # Add index for selection
            for i, b in enumerate(backups):
                b["index"] = i
                del b["mtime"]

            return {"success": True, "backups": backups}
        except OSError as e:
            return {"success": False, "error": f"List backups failed: {e}"}

    async def restore_backup(self, project_name: str, file_path: str, version_index: int = 0) -> dict:
        """Restore a file from a backup.

        Use list_backups first to see available versions.
        Index 0 is the most recent backup.

        Args:
            project_name: Name of the project
            file_path: Relative path to file
            version_index: Index of backup to restore (from list_backups). Default: 0 (newest)

        Returns:
            Success message or error
        """
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
                    backups.append((os.path.getmtime(full_path), full_path))

            if not backups:
                return {"success": False, "error": "No backups found"}

            backups.sort(reverse=True)  # newest first

            if version_index < 0 or version_index >= len(backups):
                return {"success": False, "error": f"Invalid version index. Available indices: 0 to {len(backups)-1}"}

            backup_path = backups[version_index][1]

            shutil.copy2(backup_path, file_path_str)
            return {
                "success": True,
                "message": f"Restored from {os.path.basename(backup_path)}"
            }
        except OSError as e:
            return {"success": False, "error": f"Restore failed: {e}"}

    # ==================== System Prompt ====================

    async def on_system_prompt(self) -> str:
        """Generate system prompt additions with project context."""
        output = ""

        coding_style = self.config.get("coding_style")
        if coding_style:
            output += f"\n## Coding Style\n{coding_style}\n"

        if self.config.get("add_project_list_to_system_prompt"):
            try:
                projects = [f for f in os.listdir(self.sandbox_path) if os.path.isdir(os.path.join(self.sandbox_path, f))]
                if projects:
                    output += "\n## Available Projects\n" + "\n".join(f"- {p}" for p in sorted(projects)) + "\n"
                else:
                    output += "\n## Available Projects\nNo projects exist yet. Use `create_project` to create one.\n"
            except OSError as e:
                output += f"\n## Available Projects\nCould not list projects: {e}\n"

        return output
