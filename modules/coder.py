import core
import os
import sys
import re
import subprocess
import stat
import shutil
import asyncio
import importlib
import glob as glob_module
import difflib
import time
import modules.sandboxed_files
from typing import List, Dict, Any, Optional, Union, Tuple

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
        "permissions": {
            "create_project": True,
            "add_functions": True,
            "edit_functions": True,
            "delete_functions": True,
            "create_files": True,
            "read_files": True,
            "edit_files": True,
            "overwrite_files": False,
            "execute_code": False,
        },
        "limits": {
            "folder_blacklist": ["venv"],
            "max_file_size_mb": 10,
            "max_read_lines": 5000,
            "max_grep_results": 50,
            "backup_retention_count": 5,
        }
    }

    # Language-specific formatting tools mapping
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

    # Consolidated language configuration with all metadata in one place
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.path = self.sandbox_path
        # Parser cache for performance - reuse Parser instances
        self._parser_cache = {}

        if HAS_TREE_SITTER:
            if not loaded_languages:
                core.log("coder", "Tree-sitter installed but NO language parsers found.")
            else:
                core.log("coder", f"Tree-sitter ENABLED. Languages: {loaded_languages}")
        else:
            core.log("coder", f"Tree-sitter DISABLED. Reason: {disabled_reason}")

        # Disable tools based on config
        if self.config.get("preferences", {}).get("read_only"):
            self.disabled_tools.extend([
                "add_symbol_before", "add_symbol_after", "edit_symbol",
                "delete_symbol", "create_project", "create_file",
                "overwrite_file", "execute", "edit", "append_to_file"
            ])

        if not self.config.get("permissions", {}).get("add_functions"):
            self.disabled_tools.extend(["add_symbol_before", "add_symbol_after"])

        if not self.config.get("permissions", {}).get("edit_files"):
            self.disabled_tools.extend(["edit_symbol", "edit"])

        if not self.config.get("permissions", {}).get("delete_functions"):
            self.disabled_tools.append("delete_symbol")

        if not self.config.get("permissions", {}).get("create_project"):
            self.disabled_tools.append("create_project")

        if not self.config.get("permissions", {}).get("create_files"):
            self.disabled_tools.extend(["create_file", "append_to_file"])

        if not self.config.get("permissions", {}).get("overwrite_files"):
            self.disabled_tools.append("overwrite_file")

        if not self.config.get("permissions", {}).get("execute_code"):
            self.disabled_tools.append("execute")

    # ==================== Security & Path Helpers ====================

    def _safe_path(self, *paths) -> str:
        """
        Ensure the resolved path is within the sandbox directory.
        Prevents path traversal attacks.
        """
        base = os.path.realpath(self.sandbox_path)
        target = os.path.realpath(os.path.join(base, *paths))
        if not target.startswith(base + os.sep) and target != base:
            raise ValueError(f"Path traversal detected: {target} is outside sandbox")
        return target

    def _check_file_size(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """Check if file size is within configured limits."""
        max_size_bytes = self.config.get("max_file_size_mb", 10) * 1024 * 1024
        try:
            size = os.path.getsize(file_path)
            if size > max_size_bytes:
                return False, f"File size ({size / (1024*1024):.1f}MB) exceeds limit ({self.config.get('max_file_size_mb', 10)}MB)"
            return True, None
        except OSError:
            return True, None

    # ==================== Tree-sitter Helpers ====================

    def _get_parser(self, language: str) -> Optional[Parser]:
        """Get or create a cached parser for the given language."""
        if language not in self._parser_cache:
            if language in LANGUAGE_MAP:
                self._parser_cache[language] = Parser(LANGUAGE_MAP[language])
        return self._parser_cache.get(language)

    def _parse_file(self, file_path_str: str, language: str) -> Optional[Tuple[Any, bytes]]:
        """
        Parse a file using tree-sitter. Returns (tree, source_bytes) or None on failure.
        Uses cached parsers for performance.
        """
        parser = self._get_parser(language)
        if parser is None:
            return None

        try:
            with open(file_path_str, 'rb') as f:
                source_bytes = f.read()
            tree = parser.parse(source_bytes)
            return tree, source_bytes
        except Exception as e:
            core.log("coder", f"Tree-sitter parse failed: {e}")
            return None

    def _verify_syntax(self, file_path: str) -> tuple:
        """
        Verify that a written code file has no syntax errors using tree-sitter.
        Parses the source without executing any code — language-agnostic.
        Supports all languages in LANGUAGES: python, javascript, typescript,
        html, css, cpp, c-sharp, rust, ruby, go, java.

        Returns (is_valid, error_message).
        If tree-sitter is unavailable or the language isn't recognized,
        falls back to a simple structural check; never blocks on failure.
        """
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
                error_msg = self._first_error_message(tree.root_node, source_bytes, os.path.basename(file_path))
                if error_msg:
                    return False, error_msg
                else:
                    # Fallback: provide line/column info from the error node
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
                        return False, f"Syntax error in {os.path.basename(file_path)}: line {line}, column {col}: {error_node.type} node detected"
                    return False, f"Syntax error in {os.path.basename(file_path)}: syntax error detected"

            return True, None
        except Exception as e:
            core.log("coder", f"Syntax verification skipped: {e}")
            return True, None

    def _first_error_message(self, node, source_bytes: bytes, file_name: str = "file") -> Optional[str]:
        """Walk the tree to find the first ERROR/MISSING node and produce a detailed, informative message."""
        snippet = ""
        start_line = 0
        end_line = 0
        
        # First, recursively check children for errors (depth-first)
        for child in node.children:
            msg = self._first_error_message(child, source_bytes, file_name)
            if msg:
                return msg
        
        # If this node is an error, report it
        if node.type in ('ERROR', 'MISSING'):
            start_line = node.start_point[0] + 1
            start_col = node.start_point[1] + 1
            end_line = node.end_point[0] + 1
            end_col = node.end_point[1] + 1

            # Extract the source snippet around the error
            snippet = source_bytes[node.start_byte:node.end_byte].decode('utf-8', errors='replace').strip()

            # Get surrounding context lines
            lines = source_bytes.decode('utf-8', errors='replace').split('\n')
            max_context = 3

            # Build context lines with nice formatting
            context_lines = []
            for i in range(max(0, start_line - 1 - max_context), start_line - 1):
                context_lines.append(f"    {i+1:4d}: {lines[i]}")
            err_line_str = f"  >> {start_line:4d}: {lines[start_line - 1]}"
            for i in range(start_line, min(len(lines), start_line + max_context)):
                context_lines.append(f"    {i+1:4d}: {lines[i]}")

            # Analyze the error node type and children for specific diagnostics
            error_details = self._analyze_error_node(node, snippet, lines, start_line)

            # Build a compact but informative message
            message_lines = [f"Syntax error in {file_name}:"]
            message_lines.append(f"  {error_details}")
            message_lines.append(f"  At line {start_line}, column {start_col}")

            if snippet:
                snippet_display = snippet[:50] + "..." if len(snippet) > 50 else snippet
                message_lines.append(f"  Snippet: {snippet_display!r}")

            if context_lines:
                message_lines.append(f"  Context:")
                message_lines.extend(context_lines)
                message_lines.append(err_line_str)

            if node.children and len(node.children) <= 8:
                child_types = [c.type for c in node.children]
                message_lines.append(f"  Children: {child_types}")

            return "\n".join(message_lines)

        return None

    def _analyze_error_node(self, node, snippet: str, lines: list, line_num: int) -> str:
        """Analyze an error node to provide a specific, human-readable error description."""
        children = list(node.children)

        # Check for common patterns based on language
        if node.type == 'MISSING':
            # MISSING node means parser expected something but didn't find it
            desc = self._describe_missing_token(node, lines, line_num)
            # Add context about what might be expected
            if "Missing expected token" in desc:
                expected = self._get_expected_from_children(children)
                if expected:
                    return f"Missing {expected} (expected: {desc})"
            return desc

        if node.type == 'ERROR':
            return self._describe_error_token(node, snippet, children, lines, line_num)

        # Fallback with more detail
        return f"Syntax error at line {line_num} (node type: {node.type})"

    def _describe_missing_token(self, node, lines: list, line_num: int) -> str:
        """Describe what token or structure is missing (language-agnostic)."""
        prev_line = lines[line_num - 2] if line_num > 1 else ""
        curr_line = lines[line_num - 1] if line_num <= len(lines) else ""
        next_line = lines[line_num] if line_num < len(lines) else ""

        # Check for unclosed delimiters (common across most languages)
        open_close_pairs = [('(', ')'), ('[', ']'), ('{', '}')]
        for open_char, close_char in open_close_pairs:
            if curr_line.rstrip().endswith(open_char) and not next_line.strip().endswith(close_char):
                return f"Missing closing '{close_char}' after '{open_char}'"

        # Check for unterminated string (common pattern)
        stripped = curr_line.rstrip()
        for quote in ("'", '"'):
            if stripped.count(quote) % 2 == 1:
                return f"Unterminated {quote} string literal (missing closing {quote})"

        # Check for unclosed multi-line construct (colon followed by empty next line)
        if prev_line.rstrip().endswith(':') and not next_line.strip():
            return "Missing indented block or content after ':'"

        # Check for missing comma in list/array/dict
        if next_line.strip() and not curr_line.rstrip().endswith((',', ']', '}', ')')):
            if next_line.strip().startswith((',', ']')):
                return "Missing comma before next item"

        # Check for end of file issues
        if not next_line.strip() and line_num == len(lines):
            return "Unexpected end of file (missing closing delimiters or statements)"

        # Check for missing colon after def/class/if/else/for/while
        colon_keywords = ('def', 'class', 'if', 'else', 'for', 'while', 'try', 'except', 'finally', 'with', 'elif')
        for keyword in colon_keywords:
            if curr_line.strip().startswith(keyword) and not curr_line.rstrip().endswith(':'):
                return f"Missing ':' after '{keyword}' statement"

        # Check for missing statement after return/raise/break/continue
        statement_keywords = ('return', 'raise', 'break', 'continue', 'yield')
        for keyword in statement_keywords:
            if curr_line.strip().startswith(keyword) and not curr_line.strip().endswith(('(', ':', ']', ')')):
                return f"Missing expression after '{keyword}'"

        # Generic missing token description with more context
        return f"Missing expected token or structure (at line {line_num})"

    def _describe_error_token(self, node, snippet: str, children: list, lines: list, line_num: int) -> str:
        """Describe what unexpected syntax was found (language-agnostic)."""
        if not snippet:
            expected = self._get_expected_from_children(children)
            if expected:
                return f"Unexpected empty syntax at line {line_num} (expected: {expected})"
            return f"Unexpected syntax at line {line_num} (empty error node)"

        stripped = snippet.strip()

        # Check for mismatched delimiters
        if stripped in ('(', ')', '[', ']', '{', '}'):
            # Find the matching open/close
            matching = {'(': ')', ')': '(', '[': ']', ']': '[', '{': '}', '}': '{'}
            expected_char = matching.get(stripped, '')
            return f"Unexpected '{stripped}' delimiter (expected '{expected_char}' or mismatched pair)"

        # Check for unterminated strings
        if (stripped.startswith("'") and not stripped.endswith("'")) or \
           (stripped.startswith('"') and not stripped.endswith('"')):
            quote = stripped[0]
            return f"Unterminated {quote} string literal (missing closing {quote})"

        # Check for unexpected colon (common issue in many languages)
        if stripped == ':':
            # Check if it's in a weird place
            if line_num <= len(lines):
                prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
                if prev.strip().endswith(('(', '[', '{', ',', '=')):
                    return "Unexpected ':' (may be misplaced in expression)"
            return "Unexpected ':' (may be in wrong context)"

        # Check for unexpected comma
        if stripped == ',' and line_num <= len(lines):
            prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
            if prev.endswith('(') or prev.endswith('['):
                return "Unexpected trailing comma"
            # Check if comma is at start of line after opening delimiter
            if prev.strip().endswith(('(', '[', '{')):
                return "Unexpected leading comma (may be missing previous item)"

        # Check for unexpected semicolon
        if stripped == ';' and line_num <= len(lines):
            prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
            if not prev.endswith((';', '{', '}', ')', ']')):
                return "Unexpected ';' (may be in wrong context or unnecessary)"

        # Check for unexpected comparison operator at statement level
        if stripped in ('==', '!=', '<=', '>=') and line_num <= len(lines):
            prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
            if not prev.endswith(('(', '[', ',', '=', ':')):
                return f"Unexpected '{stripped}' (may be misplaced comparison - use '=' for assignment)"

        # Check for unexpected assignment-like syntax
        if stripped == '=' and line_num <= len(lines):
            prev = lines[line_num - 2].rstrip() if line_num > 1 else ""
            if prev.endswith(('(', '[', ',', ':')):
                return "Unexpected '=' (may be a comparison instead of assignment)"

        # Check for unexpected keywords
        unexpected_keywords = ('def', 'class', 'if', 'else', 'for', 'while', 'return', 'import')
        if stripped in unexpected_keywords:
            return f"Unexpected keyword '{stripped}' (may be misplaced or missing context)"

        # If we have children, they might tell us what was expected
        if children:
            expected = self._get_expected_from_children(children)
            if expected:
                snippet_display = stripped[:30] + "..." if len(stripped) > 30 else stripped
                return f"Unexpected '{snippet_display}' (expected: {expected})"

        # Default message with more context
        snippet_display = stripped[:40] + "..." if len(stripped) > 40 else stripped
        return f"Unexpected syntax: '{snippet_display}' (at line {line_num})"

    def _get_expected_from_children(self, children: list) -> Optional[str]:
        """Try to determine what token type was expected based on children."""
        if not children:
            return None

        # If children are all terminal/error types, the parser couldn't recover
        non_error = [c for c in children if c.type not in ('ERROR', 'MISSING', '<eof>')]
        if not non_error:
            return "valid syntax"

        # Map common tree-sitter node types to human-readable names
        type_map = {
            'identifier': 'identifier/name',
            'string': 'string',
            'number': 'number',
            'comment': 'comment',
            'expression': 'expression',
            'statement': 'statement',
            'expression_statement': 'expression',
            'binary_expression': 'binary expression',
            'call_expression': 'function call',
            'member_expression': 'member access',
            'property_identifier': 'property name',
            'parameter': 'parameter',
            'return_statement': 'return statement',
            'if_statement': 'if statement',
            'for_statement': 'for statement',
            'while_statement': 'while statement',
            'function_declaration': 'function',
            'class_declaration': 'class',
            'import_statement': 'import statement',
            'import_specifier': 'import specifier',
            'keyword': 'keyword',
            'operator': 'operator',
            'punctuation': 'punctuation',
            'colon': ':',
            'semicolon': ';',
            'comma': ',',
            'left_parenthesis': '(',
            'right_parenthesis': ')',
            'left_bracket': '[',
            'right_bracket': ']',
            'left_curly_brace': '{',
            'right_curly_brace': '}',
        }

        # Return the human-readable type of the first non-error child
        child_type = non_error[0].type
        return type_map.get(child_type, child_type)

    # ==================== Language Detection ====================

    def _get_language_from_ext(self, file_path_str: str) -> str:
        """Detect language from file extension."""
        ext = os.path.splitext(file_path_str)[1].lower()
        for lang, config in self.LANGUAGES.items():
            if ext in config.get('extensions', []):
                return lang
        return 'generic'

    def _detect_language_from_content(self, content: str) -> Optional[str]:
        """
        Detect programming language from file content (shebang, magic comments, etc).
        Returns language name or None if undetectable.
        """
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
                elif 'perl' in line:
                    return 'perl'
            # Language magic comments
            if '// @ts-check' in line or '// TypeScript' in line:
                return 'typescript'
            if '# -*- coding: python' in line:
                return 'python'
            if '<?php' in line:
                return 'php'
            if '# language:ruby' in line:
                return 'ruby'
        return None

    def _detect_language(self, file_path_str: str, content: str = None) -> str:
        """Detect language from extension first, then content as fallback."""
        lang = self._get_language_from_ext(file_path_str)
        if lang != 'generic' and lang in LANGUAGE_MAP:
            return lang
        if content:
            detected = self._detect_language_from_content(content)
            if detected and detected in self.LANGUAGES:
                return detected
        return lang

    # ==================== Backup & Undo System ====================

    def _get_backup_dir(self) -> str:
        """Get the backup directory path."""
        backup_dir = os.path.join(self.sandbox_path, ".backups")
        os.makedirs(backup_dir, exist_ok=True)
        return backup_dir

    async def _backup_file(self, file_path: str) -> Optional[str]:
        """
        Create a timestamped backup for undo support.
        Returns the backup path or None if backup failed.
        Enforces retention limit to prevent disk bloat.
        """
        if not os.path.exists(file_path):
            return None

        try:
            backup_dir = self._get_backup_dir()
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            basename = os.path.basename(file_path)
            backup_name = f"{basename}.{timestamp}.bak"
            backup_path = os.path.join(backup_dir, backup_name)
            shutil.copy2(file_path, backup_path)

            # Enforce retention limit
            self._cleanup_old_backups(basename)
            return backup_path
        except Exception as e:
            core.log("coder", f"Backup failed: {e}")
            return None

    def _cleanup_old_backups(self, basename: str, max_count: int = None):
        """Remove old backups beyond the retention limit."""
        max_count = max_count or self.config.get("backup_retention_count", 5)
        backup_dir = self._get_backup_dir()
        try:
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith(basename + ".") and f.endswith(".bak"):
                    full_path = os.path.join(backup_dir, f)
                    backups.append((os.path.getmtime(full_path), full_path))

            backups.sort(reverse=True)  # newest first
            for _, path in backups[max_count:]:
                os.remove(path)
        except Exception as e:
            core.log("coder", f"Backup cleanup failed: {e}")

    async def restore_backup(self, project_name: str, file_path: list) -> dict:
        """Restores a file from backup. If backup_path is None, restores from the most recent backup."""
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
            backups.sort(reverse=True)
            backup_path = backups[0][1]

            shutil.copy2(backup_path, file_path_str)
            return {
                "success": True,
                "message": f"Restored from {os.path.basename(backup_path)}"
            }
        except Exception as e:
            return {"success": False, "error": f"Restore failed: {e}"}

    # ==================== Symbol Helpers ====================

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

    def _find_symbol_line(self, file_path_str: str, symbol_name: str, language: str) -> Optional[int]:
        """Helper to find the line number of a symbol by its name."""
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                result = self._parse_file(file_path_str, language)
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
                    return target_node.start_point[0] + 1
            except Exception:
                pass

        # Fallback to Regex
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

    def _find_symbol_end_line(self, lines, start_idx: int, body_type: str) -> int:
        """
        Find the end line of a symbol given its start line.
        Handles indentation-based (Python, Ruby) and brace-based (C-style) languages.
        Properly handles braces inside strings and comments.
        """
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
            # Brace-based: need to handle braces inside strings and comments
            brace_count = 0
            in_string = None  # Current string delimiter or None
            in_line_comment = False
            in_block_comment = False
            start_brace_idx = -1

            for i in range(start_idx, len(lines)):
                line = lines[i]
                j = 0
                while j < len(line):
                    char = line[j]

                    # Handle block comments (/* ... */)
                    if in_block_comment:
                        if char == '*' and j + 1 < len(line) and line[j + 1] == '/':
                            in_block_comment = False
                            j += 2
                            continue
                        j += 1
                        continue

                    # Handle line comments
                    if in_line_comment:
                        if char == '\n':
                            in_line_comment = False
                        j += 1
                        continue

                    # Handle string literals
                    if in_string:
                        if char == '\\' and j + 1 < len(line):
                            j += 2  # Skip escaped character
                            continue
                        if char == in_string:
                            in_string = None
                        j += 1
                        continue

                    # Check for string/comment start
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

                    # Count braces (only outside strings/comments)
                    if char == '{':
                        if start_brace_idx == -1:
                            start_brace_idx = i
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count <= 0:
                            return i + 1

                    j += 1

            # If no closing brace found, return rest of file
            if start_brace_idx == -1:
                return start_idx + 1
            return len(lines)

    def _get_symbol_nodes(self, file_path_str: str, symbol_name: str, language: str):
        """
        Get candidate tree-sitter nodes for a symbol.
        Returns list of (node, source_bytes) tuples.
        """
        if not (HAS_TREE_SITTER and language in LANGUAGE_MAP):
            return []

        result = self._parse_file(file_path_str, language)
        if result is None:
            return []

        tree, source_bytes = result
        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
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

        # Return the most precise match (smallest node)
        best_node = min(candidate_nodes, key=lambda n: n.end_byte - n.start_byte)
        return [(best_node, source_bytes)]

    # ==================== File Path Helpers ====================

    def _get_project_path(self, name: str) -> str:
        return self._get_sandbox_path(name)

    def _get_file_path(self, project_name: str, file_path: list) -> str:
        rel_path = os.path.join(project_name, *file_path)
        return self._get_sandbox_path(rel_path)

    # ==================== File Operations ====================

    async def list_full_project_tree(self, project_name: str, depth_limit: int = 3):
        """Returns a recursive tree representation of the project structure. Use this to understand the overall project layout before diving into specific files."""
        project_path = self._get_project_path(project_name)
        if not os.path.exists(project_path):
            return self.result({"success": False, "error": "project does not exist"})

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
            return self.result({"success": True, "tree": tree})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def list_project_folder(self, project_name: str, sub_path: list = None):
        """Lists the immediate contents of a specific path within a project (non-recursive)."""
        sub_path = sub_path or []
        target_path = self._get_project_path(project_name)
        if sub_path:
            target_path = os.path.join(target_path, *sub_path)

        if not os.path.exists(target_path):
            return self.result({"success": False, "error": "path does not exist"})
        if not os.path.isdir(target_path):
            return self.result({"success": False, "error": "path is not a directory"})

        try:
            return self.result({"success": True, "contents": os.listdir(target_path)})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def create_project(self, project_name: str):
        if not self.config.get("permissions").get("create_project"):
            return self.result({"success": False, "error": "Project creation is disabled."})

        base_path = self._get_project_path(project_name)

        if os.path.exists(base_path):
            return self.result("Project already exists! Choose a different name.", False)

        try:
            os.makedirs(base_path, exist_ok=True)
            return self.result({"success": True, "message": f"Project '{project_name}' created."})
        except OSError as e:
            return self.result({"success": False, "error": f"Error creating project: {e}"})

    async def create_file(self, project_name: str, file_path: list, content: str):
        """Creates a file at specified path. Path will be recursively created if nonexistent."""

        if not self.config.get("permissions").get("create_files"):
            return self.result({"success": False, "error": "File creation is disabled"})

        file_path_str = self._get_file_path(project_name, file_path)

        if os.path.exists(file_path_str):
            return self.result({"success": False, "error": f"File already exists."})

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)

            # Verify syntax
            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The file was created but contains syntax errors."
                })

            return self.result({"success": True, "message": f"File created."})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def read_file(self, project_name: str, file_path: list, offset: int = None, limit: int = None):
        if not self.config.get("permissions").get("read_files"):
            return self.result({"success": False, "error": "Full file reading is disabled. Use get_symbol!"})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist!"})

        # Check file size
        size_ok, size_error = self._check_file_size(file_path_str)
        if not size_ok:
            return self.result({"success": False, "error": size_error})

        try:
            with open(file_path_str, "r", encoding='utf-8') as f:
                lines = f.readlines()

            total_lines = len(lines)
            max_lines = self.config.get("max_read_lines", 5000)

            # Apply offset (1-indexed)
            start_idx = 0
            if offset is not None:
                start_idx = max(0, min(offset - 1, total_lines))

            # Apply limit
            end_idx = total_lines
            if limit is not None:
                end_idx = min(start_idx + limit, total_lines)

            # Enforce max lines
            if (end_idx - start_idx) > max_lines:
                end_idx = start_idx + max_lines

            selected_lines = lines[start_idx:end_idx]
            result = "".join(selected_lines)

            # Truncate if too large (50KB)
            max_bytes = 50 * 1024
            truncated = False
            if len(result.encode('utf-8')) > max_bytes:
                while len(result.encode('utf-8')) > max_bytes and result:
                    result = result[:-1]
                truncated = True

            response = result
            if truncated:
                response += "\n\n[Output truncated - file has more content]"

            return response
        except Exception as e:
            return self.result({"success": False, "error": f"error reading file: {e}"})

    async def overwrite_file(self, project_name: str, file_path: list, content: str):
        """Completely overwrites an existing file with new content."""
        if not self.config.get("permissions").get("overwrite_files"):
            return self.result({"success": False, "error": "File overwriting is disabled. Use edit_symbol!"})

        file_path_str = self._get_file_path(project_name, file_path)

        # Create backup before overwriting
        await self._backup_file(file_path_str)

        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        try:
            with open(file_path_str, "w", encoding='utf-8') as f:
                f.write(content)

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The file was written but contains syntax errors."
                })

            return self.result({"success": True, "message": f"File overwritten at {file_path_str}"})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def append_to_file(self, project_name: str, file_path: list, content: str):
        if not self.config.get("permissions").get("edit_files"):
            return self.result({"success": False, "error": "File creation/editing is disabled"})

        file_path_str = self._get_file_path(project_name, file_path)
        target_dir = os.path.dirname(file_path_str)
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        mode = 'a'
        if not os.path.exists(file_path_str):
            mode = 'w'

        try:
            with open(file_path_str, mode, encoding='utf-8') as f:
                if mode == 'a' and os.path.getsize(file_path_str) > 0:
                    f.write('\n')
                f.write(content)
                if not content.endswith('\n'):
                    f.write('\n')

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The content was appended but the file contains syntax errors."
                })

            return self.result({"success": True, "message": f"Content appended to {file_path_str}"})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    # ==================== Code Execution ====================

    async def execute(self, project_name: str, file_path: list, timeout: int = 30):
        if not self.config.get("permissions").get("execute_code"):
            return self.result({"success": False, "error": "Code execution is disabled for security."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist!"})

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
                    return self.result({
                        "success": False,
                        "error": f"Error (exit code {proc.returncode})",
                        "stdout": stdout_str,
                        "stderr": stderr_str
                    })

                return self.result({
                    "success": True,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "returncode": proc.returncode
                })
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                    await proc.wait()
                except:
                    pass
                return self.result({"success": False, "error": f"Execution timed out after {timeout} seconds"})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    # ==================== Symbol Operations ====================

    async def get_outline(self, project_name: str, file_path: list, language: str = None):
        """Returns a list of symbols (classes, functions, etc.) in a file. USE THIS FIRST to understand what's in a file before reading specific symbols."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            try:
                result = self._parse_file(file_path_str, language)
                if result is not None:
                    tree, source_bytes = result
                    symbols = []
                    self._walk_for_symbols(tree.root_node, language, symbols)
                    symbols.sort(key=lambda x: x['line'])
                    return self.result({
                        "success": True,
                        "symbols": [{"name": s["name"], "type": s["type"]} for s in symbols]
                    })
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
            return self.result({"success": True, "symbols": outline})
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def get_symbol(self, project_name: str, file_path: list, symbol_name: str, language: str = None):
        """Returns the code block for a symbol by name. THIS IS THE PREFERRED WAY TO READ CODE."""
        file_path_str = self._get_file_path(project_name, file_path)

        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        if not language:
            language = self._get_language_from_ext(file_path_str)

        # 1. Try Tree-sitter
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                found_code = source_bytes[node.start_byte:node.end_byte].decode('utf-8')
                return found_code

        # 2. Fallback to line-based extraction
        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result({"success": False, "error": f"symbol '{symbol_name}' not found"})

        lang_config = self.LANGUAGES.get(language, {})
        body_type = lang_config.get('body_type', 'brace')

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result({"success": False, "error": "line number out of range"})

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
                end_idx = self._find_symbol_end_line(lines, start_idx, body_type)
                body_lines = lines[start_idx:end_idx]

            return "".join(body_lines)
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def edit_symbol(self, project_name: str, file_path: list, symbol_name: str, new_content: str, language: str = None):
        if not self.config.get("permissions").get("edit_functions"):
            return self.result({"success": False, "error": "Symbol editing is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        await self._backup_file(file_path_str)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result({"success": False, "error": f"symbol '{symbol_name}' not found"})

        # 1. Try Tree-sitter for precise byte-level replacement
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                new_content_bytes = new_content.encode('utf-8')
                updated_bytes = source_bytes[:node.start_byte] + new_content_bytes + source_bytes[node.end_byte:]

                with open(file_path_str, 'wb') as f:
                    f.write(updated_bytes)

                is_valid, error = self._verify_syntax(file_path_str)
                if not is_valid:
                    return self.result({
                        "success": False,
                        "error": error,
                        "message": "The edit was applied but the file contains syntax errors."
                    })

                return self.result({
                    "success": True,
                    "message": f"Symbol '{symbol_name}' edited in {os.path.join(project_name, *file_path)}"
                })

        # 2. Fallback to line-based replacement
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result({"success": False, "error": "line number out of range"})

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

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The edit was applied but the file contains syntax errors."
                })

            return self.result({
                "success": True,
                "message": f"Symbol '{symbol_name}' edited in {os.path.join(project_name, *file_path)}"
            })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def add_symbol_before(self, project_name: str, file_path: list, target_symbol_name: str, name: str, content_body: str, language: str = None):
        if not self.config.get("permissions").get("add_functions"):
            return self.result({"success": False, "error": "Symbol adding is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result({"success": False, "error": f"symbol '{target_symbol_name}' not found"})

        # Validate the new symbol name matches the content
        if name:
            lang_config = self.LANGUAGES.get(language, {})
            patterns = lang_config.get('outline_patterns', [])
            content_valid = False
            for pattern, sym_type in patterns:
                if re.search(pattern, content_body):
                    content_valid = True
                    break
            if not content_valid and not any(c.isalnum() for c in name):
                core.log("coder", f"Warning: symbol name '{name}' may not match content")

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

            # Ensure there's a newline before the insertion point
            insert_pos = line_number - 1
            if insert_pos > 0 and not lines[insert_pos - 1].endswith('\n'):
                lines.insert(insert_pos, '\n')
                insert_pos += 1

            lines.insert(insert_pos, new_symbol)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The symbol was added but the file contains syntax errors."
                })

            return self.result({
                "success": True,
                "message": f"Symbol '{name}' added before '{target_symbol_name}'"
            })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def add_symbol_after(self, project_name: str, file_path: list, target_symbol_name: str, name: str, content_body: str, language: str = None):
        if not self.config.get("permissions").get("add_functions"):
            return self.result({"success": False, "error": "Symbol adding is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, target_symbol_name, language)
        if not line_number:
            return self.result({"success": False, "error": f"symbol '{target_symbol_name}' not found"})

        # Validate the new symbol name
        if name:
            lang_config = self.LANGUAGES.get(language, {})
            patterns = lang_config.get('outline_patterns', [])
            content_valid = False
            for pattern, sym_type in patterns:
                if re.search(pattern, content_body):
                    content_valid = True
                    break
            if not content_valid and not any(c.isalnum() for c in name):
                core.log("coder", f"Warning: symbol name '{name}' may not match content")

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

            # Ensure there's a newline before the insertion point
            if end_idx > 0 and not lines[end_idx - 1].endswith('\n'):
                lines.insert(end_idx, '\n')
                end_idx += 1

            lines.insert(end_idx, new_symbol)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The symbol was added but the file contains syntax errors."
                })

            return self.result({
                "success": True,
                "message": f"Symbol '{name}' added after '{target_symbol_name}'"
            })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def delete_symbol(self, project_name: str, file_path: list, symbol_name: str, language: str = None):
        if not self.config.get("permissions").get("edit_functions"):
            return self.result({"success": False, "error": "Symbol deletion is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        await self._backup_file(file_path_str)

        if not language:
            language = self._get_language_from_ext(file_path_str)

        line_number = self._find_symbol_line(file_path_str, symbol_name, language)
        if not line_number:
            return self.result({"success": False, "error": f"symbol '{symbol_name}' not found"})

        # 1. Try Tree-sitter for precise removal
        if HAS_TREE_SITTER and language in LANGUAGE_MAP:
            nodes = self._get_symbol_nodes(file_path_str, symbol_name, language)
            if nodes:
                node, source_bytes = nodes[0]
                updated_bytes = source_bytes[:node.start_byte] + source_bytes[node.end_byte:]

                with open(file_path_str, 'wb') as f:
                    f.write(updated_bytes)

                is_valid, error = self._verify_syntax(file_path_str)
                if not is_valid:
                    return self.result({
                        "success": False,
                        "error": error,
                        "message": "The symbol was deleted but the file contains syntax errors."
                    })

                return self.result({
                    "success": True,
                    "message": f"Symbol '{symbol_name}' deleted from {os.path.join(project_name, *file_path)}"
                })

        # 2. Fallback to line-based removal
        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            if not (1 <= line_number <= len(lines)):
                return self.result({"success": False, "error": "line number out of range"})

            lang_config = self.LANGUAGES.get(language, {})
            body_type = lang_config.get('body_type', 'brace')

            start_idx = line_number - 1
            end_idx = self._find_symbol_end_line(lines, start_idx, body_type)

            del lines[start_idx:end_idx]

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The symbol was deleted but the file contains syntax errors."
                })

            return self.result({
                "success": True,
                "message": f"Symbol '{symbol_name}' deleted from {os.path.join(project_name, *file_path)}"
            })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    # ==================== Search Operations ====================

    async def search(self, project_name: str, file_path: list, query: str, context_lines: int = 5, max_matches: int = 10, use_regex: bool = False):
        """Searches for text or regex pattern within a file. Returns snippets with line numbers and surrounding context."""
        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist!"})

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            matches = []
            num_lines = len(lines)

            if use_regex:
                try:
                    pattern = re.compile(query, re.IGNORECASE)
                except re.error as e:
                    return self.result({"success": False, "error": f"Invalid regex pattern: {e}"})
            else:
                query_lower = query.lower()

            for i, line in enumerate(lines):
                if len(matches) >= max_matches:
                    break

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

            if not matches:
                return self.result({
                    "success": True,
                    "matches": 0,
                    "file": os.path.join(project_name, *file_path)
                })

            result_str = "\n\n".join(matches)
            return self.result({
                "success": True,
                "matches": len(matches),
                "file": os.path.join(project_name, *file_path),
                "results": result_str
            })

        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    def _generate_diff(self, orig_content: str, new_content: str):
        # Generate unified diff
        orig_lines = orig_content.splitlines(keepends=True)
        mod_lines = content.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            mod_lines,
            fromfile=f"{project_name}/{os.path.join(*file_path)}",
            tofile=f"{project_name}/{os.path.join(*file_path)} (modified)",
            lineterm=''
        )
        diff_str = "\n".join(diff)

    async def edit(self, project_name: str, file_path: list, old_text: str, new_text: str):
        if not self.config.get("permissions").get("edit_files"):
            return self.result({"success": False, "error": "Editing is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        await self._backup_file(file_path_str)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                content = f.read()

            if old_text not in content:
                return self.result({
                    "success": False,
                    "error": f"old_text for edit not found in file. "
                    f'The exact text "{old_text[:80]}{"..." if len(old_text) > 80 else ""}" '
                    f'was not found. Make sure old_text matches exactly including whitespace.'
                })

            content = content.replace(old_text, new_text, 1)

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.write(content)

            is_valid, error = self._verify_syntax(file_path_str)
            if not is_valid:
                return self.result({
                    "success": False,
                    "error": error,
                    "message": "The edit was applied but the file contains syntax errors."
                })

            return self.result({
                "success": True,
                "message": f"Successfully applied edit to {os.path.join(project_name, *file_path)}"
            })

        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def grep(self, project_name: str, path: list = None, pattern: str = "", use_regex: bool = False,
                   case_sensitive: bool = False, max_results: int = None):
        """Searches within a directory using a pattern. Pattern can be normal string or regex."""

        search_dir = self._get_project_path(project_name)
        if path:
            search_dir = os.path.join(search_dir, *path)

        if not os.path.isdir(search_dir):
            return self.result({"success": False, "error": "search directory does not exist"})

        max_results = max_results or self.config.get("max_grep_results", 50)

        try:
            if use_regex:
                flags = 0 if case_sensitive else re.IGNORECASE
                try:
                    compiled_pattern = re.compile(pattern, flags)
                except re.error as e:
                    return self.result({"success": False, "error": f"Invalid regex pattern: {e}"})
            else:
                search_text = pattern if case_sensitive else pattern.lower()

            results = []
            file_count = 0
            total_matches = 0

            for root, dirs, files in os.walk(search_dir):
                # Skip hidden and non-source directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != 'venv' and d != '__pycache__' and d != '.git']

                for filename in sorted(files):
                    filepath = os.path.join(root, filename)
                    rel_path = os.path.relpath(filepath, search_dir)

                    # Skip binary files
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ('.pyc', '.pyo', '.so', '.dll', '.exe', '.bin', '.db', '.sqlite'):
                        continue

                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                            for line_num, line in enumerate(f, 1):
                                found = False
                                if use_regex:
                                    if compiled_pattern.search(line):
                                        found = True
                                else:
                                    line_search = line.lower() if not case_sensitive else line
                                    if search_text in line_search:
                                        found = True

                                if found:
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

            return self.result({
                "success": True,
                "pattern": pattern,
                "matches": min(total_matches, max_results),
                "files_searched": file_count,
                "truncated": total_matches > max_results,
                "results": results[:max_results]
            })

        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def find_files(self, project_name: str, path: list = None, pattern: str = "*", file_type: str = "any"):
        """Finds files matching a glob pattern in a project."""
        search_dir = self._get_project_path(project_name)
        if path:
            search_dir = os.path.join(search_dir, *path)

        if not os.path.exists(search_dir):
            return self.result({"success": False, "error": "search directory does not exist"})

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
                results.append(rel_path)

            return self.result({
                "success": True,
                "pattern": pattern,
                "count": len(results),
                "files": sorted(results)
            })

        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    # ==================== Formatting & Imports ====================

    async def format_file(self, project_name: str, file_path: list, formatter: str = "auto") -> dict:
        """Formats code using appropriate formatter. Supports: auto, black, autopep8, prettier, gofmt, rustfmt, clang-format, etc."""
        if not self.config.get("permissions").get("edit_files"):
            return self.result({"success": False, "error": "Editing is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        await self._backup_file(file_path_str)

        try:
            lang = self._get_language_from_ext(file_path_str)
            formatters = self.FORMATTERS.get(lang, [])

            async def run_formatter(fmt_name, args):
                """Run a formatter with given args, handling CLI differences."""
                proc = await asyncio.create_subprocess_exec(
                    fmt_name, *args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
                    return proc.returncode, stdout, stderr
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                        await proc.wait()
                    except:
                        pass
                    return -1, b"", b"Timeout"

            def try_format_with_inplace(fmt_name):
                """Try formatting with -i flag, fallback to read/write if it fails."""
                import subprocess as sp
                try:
                    # Try with -i first
                    result = sp.run([fmt_name, "-i", file_path_str], 
                                   capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        return True, fmt_name
                except (FileNotFoundError, sp.TimeoutExpired):
                    pass
                
                # Fallback: read, format, write
                try:
                    with open(file_path_str, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Try running without -i (pipe mode)
                    result = sp.run([fmt_name, '-'], 
                                   input=content, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        with open(file_path_str, 'w', encoding='utf-8') as f:
                            f.write(result.stdout)
                        return True, fmt_name
                except (FileNotFoundError, sp.TimeoutExpired):
                    pass
                
                return False, None

            if formatter == "auto":
                # Try each formatter until one succeeds
                for fmt in formatters:
                    success, used_fmt = try_format_with_inplace(fmt)
                    if success:
                        return self.result({
                            "success": True,
                            "message": f"File formatted with {used_fmt}",
                            "formatter": used_fmt
                        })
                return self.result({
                    "success": False,
                    "error": f"No formatter found for {lang}. Tried: {formatters}"
                })
            else:
                # Use specified formatter
                if formatter not in formatters:
                    return self.result({
                        "success": False,
                        "error": f"Formatter '{formatter}' not supported for {lang}. Supported: {formatters}"
                    })

                success, used_fmt = try_format_with_inplace(formatter)
                if success:
                    return self.result({
                        "success": True,
                        "message": f"File formatted with {used_fmt}",
                        "formatter": used_fmt
                    })
                
                return self.result({
                    "success": False,
                    "error": f"Formatter '{formatter}' failed for {lang}."
                })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    async def update_python_imports(self, project_name: str, file_path: list, added_symbols: list = None, removed_symbols: list = None, language: str = None) -> dict:
        """Updates import statements when symbols are added or removed. Currently only handles Python imports."""
        if not self.config.get("permissions").get("edit_files"):
            return self.result({"success": False, "error": "Editing is disabled."})

        file_path_str = self._get_file_path(project_name, file_path)
        if not os.path.exists(file_path_str):
            return self.result({"success": False, "error": "file does not exist"})

        if not language:
            language = self._get_language_from_ext(file_path_str)

        if language != 'python':
            return self.result({
                "success": False,
                "error": f"Import management is only implemented for Python. Got: {language}"
            })

        await self._backup_file(file_path_str)

        try:
            with open(file_path_str, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Find import block - more robust detection
            imports_start = None
            imports_end = None
            import_pattern = re.compile(r'^(?:import\s+|from\s+\S+\s+import\s+)')
            
            for i, line in enumerate(lines):
                if import_pattern.match(line):
                    if imports_start is None:
                        imports_start = i
                    imports_end = i + 1
                elif imports_start is not None and line.strip() and not line.strip().startswith('#'):
                    # Stop at first non-import, non-blank, non-comment line
                    break

            if imports_start is None:
                # No imports found
                if not added_symbols:
                    return self.result({
                        "success": True,
                        "message": "No imports found in file",
                        "changes_made": 0
                    })
                # If adding symbols, we need to create import block
                imports_start = 0
                imports_end = 0
                # Find first non-import line to insert before
                for i, line in enumerate(lines):
                    if not line.strip().startswith('#') and not line.strip().startswith('import') and not line.strip().startswith('from'):
                        imports_start = i
                        imports_end = i
                        break
                else:
                    # File is empty or only comments
                    imports_start = 0
                    imports_end = 0

            import_lines = lines[imports_start:imports_end] if imports_start is not None else []
            changes_made = 0

            # Parse existing imports to build a set of (module, name) tuples
            existing_imports = set()  # (module, name) where name is None for module imports
            for line in import_lines:
                # Handle 'from X import Y, Z'
                match = re.search(r'^from\s+(\S+)\s+import\s+(.+)', line)
                if match:
                    module = match.group(1)
                    names = [n.strip().split(' as ')[0].strip() for n in match.group(2).split(',')]
                    for name in names:
                        if name:
                            existing_imports.add((module, name))
                    # Also add the module itself if it's a relative import
                    if module.startswith('.'):
                        existing_imports.add((module, None))
                # Handle 'import X, Y'
                match = re.search(r'^import\s+(.+)', line)
                if match:
                    modules = [m.strip().split(' as ')[0].strip() for m in match.group(1).split(',')]
                    for mod in modules:
                        if mod:
                            existing_imports.add((mod, None))

            # Remove imports for deleted symbols
            if removed_symbols:
                new_import_lines = []
                for line in import_lines:
                    should_remove = False
                    for sym in removed_symbols:
                        # Check for exact symbol match in import
                        if re.search(rf'\b{re.escape(sym)}\b', line):
                            should_remove = True
                            break
                    if not should_remove:
                        new_import_lines.append(line)
                    else:
                        changes_made += 1
                import_lines = new_import_lines

            # Re-parse existing imports after removal
            existing_imports = set()
            for line in import_lines:
                match = re.search(r'^from\s+(\S+)\s+import\s+(.+)', line)
                if match:
                    module = match.group(1)
                    names = [n.strip().split(' as ')[0].strip() for n in match.group(2).split(',')]
                    for name in names:
                        if name:
                            existing_imports.add((module, name))
                    if module.startswith('.'):
                        existing_imports.add((module, None))
                match = re.search(r'^import\s+(.+)', line)
                if match:
                    modules = [m.strip().split(' as ')[0].strip() for m in match.group(1).split(',')]
                    for mod in modules:
                        if mod:
                            existing_imports.add((mod, None))

            # Add imports for new symbols
            if added_symbols:
                # Group symbols by module for cleaner imports
                symbols_by_module = {}
                for sym in added_symbols:
                    # Check if already imported
                    already_imported = False
                    for (module, name) in existing_imports:
                        if name == sym or module == sym:
                            already_imported = True
                            break
                    
                    if not already_imported:
                        # Try to find which module it belongs to
                        # Default to current module (.)
                        symbols_by_module.setdefault('.', []).append(sym)

                for module, syms in symbols_by_module.items():
                    if len(syms) == 1:
                        import_lines.append(f"from {module} import {syms[0]}\n")
                    else:
                        import_lines.append(f"from {module} import {', '.join(syms)}\n")
                    changes_made += 1

            # Clean up empty lines in import block
            while import_lines and not import_lines[-1].strip():
                import_lines.pop()
            if import_lines and not import_lines[-1].endswith('\n'):
                import_lines[-1] += '\n'

            lines[imports_start:imports_end] = import_lines

            with open(file_path_str, 'w', encoding='utf-8') as f:
                f.writelines(lines)

            return self.result({
                "success": True,
                "message": f"Updated {changes_made} import(s)",
                "changes_made": changes_made
            })
        except Exception as e:
            return self.result({"success": False, "error": str(e)})

    # ==================== System Prompt ====================

    async def on_system_prompt(self):
        output = """## Code Editing Tool Usage
- Reading: 1. **get_outline** -> 2. **get_symbol** -> 3. **read_file** (offset/limit) -> 4. **read_file** (full, LAST RESORT)
- Editing: 1. **edit** (preferred, exact text replacement, batches allowed) -> 2. **append_to_file** -> 3. **edit_symbol**/add_*
- Searching: 1. **grep** (across files) -> 2. **find_files** (glob) -> 3. **search** (single file) -> 4. **list_full_project_tree**

## Content Format
RAW source code only. Use actual newlines/quotes. Do NOT escape as `\\n` or `\\\"`.
""".strip()
        coding_style = self.config.get("coding_style")
        if coding_style: output += f"\n## Coding Style\n{coding_style}\n"
        try:
            projects = [f for f in os.listdir(self.sandbox_path) if os.path.isdir(os.path.join(self.sandbox_path, f))]
            output += "## Projects in Sandbox\n" + ("\n".join(f"- {p}" for p in projects) if projects else "- No projects exist. Use `create_project` to create one.\n")
        except Exception as e:
            output += f"Could not list projects: {e}\n"
        if HAS_TREE_SITTER:
            output += f"\n## Parser Support\nTree-sitter enabled for: {', '.join(loaded_languages)}"
        else:
            output += f"\n## Parser Support\nTree-sitter disabled: {disabled_reason}"
        return output
