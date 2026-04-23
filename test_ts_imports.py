#!/usr/bin/env python3
import importlib

languages_to_test = [
    'tree_sitter_python',
    'tree_sitter_javascript',
    'tree_sitter_typescript',
    'tree_sitter_cpp',
    'tree_sitter_go',
    'tree_sitter_java',
    'tree_sitter_rust',
    'tree_sitter_c_sharp',
    'tree_sitter_ruby'
]

for lang in languages_to_test:
    try:
        importlib.import_module(lang)
        print(f"{lang} is AVAILABLE")
    except ImportError:
        print(f"{lang} is NOT available")
