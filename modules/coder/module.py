import core
import channels.webui.api as webui
import os
import errno
import importlib
import shutil
import regex
import glob
import fnmatch
import difflib
import asyncio
import subprocess
import tree_sitter_language_pack as tslp

def _nofollow_open(path: str, mode: str = "r", base: str = None):
    """
    a wrapper around os open() that refuses to follow symlinks.
    because security!
    """
    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) status:reviewed harness:openlumara

    flags = 0
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW

    if "x" in mode:
        flags |= os.O_WRONLY | os.O_CREAT | os.O_EXCL
    elif "w" in mode:
        flags |= os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    elif "r" in mode:
        flags |= os.O_RDONLY
    else:
        raise ValueError(f"unsupported open mode: {mode}")

    try:
        if base is not None:
            # kernel-enforced, component-by-component (sandbox_open adds O_NOFOLLOW itself)
            fd = core.sandbox_open(base, path, flags, 0o666)
        else:
            # 0o666 matches plain open(): the umask still applies as usual
            fd = os.open(path, flags, 0o666)
    except OSError as e:
        # make the ELOOP from O_NOFOLLOW read like the sandbox's own message
        # instead of "Too many levels of symbolic links"
        if e.errno == getattr(errno, "ELOOP", None):
            raise ValueError("Symlinks are not allowed in the requested path")
        raise

    # fdopen has no 'x' mode; the O_EXCL already happened in os.open
    fdopen_mode = mode.replace("x", "w")
    if "b" in mode:
        return os.fdopen(fd, fdopen_mode)
    return os.fdopen(fd, fdopen_mode, encoding="utf-8")


class Coder(core.module.Module):
    """Lets your AI write code within sandboxes, without using a shell. Validates code syntax before writing to disk to protect your code from breaking."""

    category = "development"

    # The coder module, now manually rewritten and free of any AI slop :)
    # ~ Rose22

    settings = {
        "read-only": {
            "default": False,
            "description": "Disables all operations that could modify your code or your filesystem. You can use `/coder readonly` to quickly toggle this during sessions."
        },
        "global_line_limit": {
            "default": 1000,
            "description": "Hard limit on the amount of lines the AI is allowed to read at once. Greatly helps reduce token usage!"
        },

        # paths
        "sandbox_paths": {
            "default": ["sandbox/coder_sandbox"],
            "description": "Paths to folders you want the coder to have access to. You can use the `~` character to refer to your home folder, such as `/home/you` on linux, /Users/You on mac, `C:\\Users\\You` on windows"
        },

        "template_paths": {
            "default": [],
            "description": "Templates are special files that the coder can read from anywhere at any time when requested, in order to show example code to the AI. You can define folders to load such templates from here!"
        },
        "enable_builtin_templates": {
            "default": True,
            "description": "Openlumara comes bundled with hand-written templates for creating your own modules and channels! Enable them here.\n\n**TIP**: To vibecode your own modules or channels, tell the AI to read the module or channel template in your prompt. Example: `read the openlumara channel template and make me a basic terminal user interface`"
        },

        "use_coding_prompt": {
            "default": False,
            "description": "If enabled, will allow you to specify a special prompt that instructs the AI on your preferred coding practices and guidelines."
        },
        "coding_prompt": {
            "type": "long_text",
            "default": "",
            "depends": "use_coding_prompt"
        },

        # flags
        "insert_sandbox_paths_into_system_prompt": {
            "default": True,
            "description": "Puts the list of sandboxes into the AI's system prompt so that it is always aware of which paths it can access. Recommended!"
        },
        "add_sandbox_contents_to_sandbox_list": {
            "default": False,
            "description": "Puts a list of top-level folders within each sandbox into the system prompt. This greatly speeds up sandbox exploration, and is not a recursive list - it only lists the folders that are directly at the root level of each sandbox.",
            "depends": "insert_sandbox_paths_into_system_prompt"
        },

        # webui editor extensions (umbrella toggle is auto-detected from the module's webui folder)
        "editor_mode": {
            "default": "standard",
            "type": "select",
            "description": "Keybinding scheme for the webui file editor.",
            "options": {
                "standard": "Standard CodeMirror bindings (no special emulation)",
                "vim": "Vim keybindings",
                "emacs": "Emacs-style bindings",
                "sublime": "Sublime Text-style bindings",
                "nano": "GNU nano bindings",
            },
            "depends": "enable_webui_extension"
        },
        "autosave_interval": {
            "default": 0,
            "description": "Auto-save files after this many seconds of inactivity (0 = disabled). Only applies to the webui editor.",
            "depends": "enable_webui_extension"
        },
        "show_welcome_card": {
            "default": True,
            "description": "Show the coder card on the webui welcome screen: the resume-last-file row, pinned + recent files and the git strip.",
            "depends": "enable_webui_extension"
        },
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        "git_keep_committed_visible": {
            "default": True,
            "description": "Git sidebar behavior after a commit.\n\n**On (new way)**: committed-but-unpushed files STAY in the changes list with a violet 'committed' dot, so nothing you wrote silently vanishes before it ships - they leave the list when you push.\n\n**Off (classic)**: committing removes files from the list immediately, plain `git status` style.",
            "depends": "enable_webui_extension"
        },

        # blacklists
        "folder_blacklist": {
            "default": ["venv", "__pycache__"],
            "description": "Prevents recursive operations such as `glob` and `grep` from reaching into folders matching the names in this blacklist"
        }
    }

    # the coder likes sitting on a tree... of code
    # the tree is nice and green and it also tells the coder whether it made any oopsies
    dependencies = [
        "tree-sitter",
        "tree-sitter-language-pack",
    ]

    regex_timeout = 3
    builtin_templates_path = "modules/coder/templates"

    # -------------
    # events
    # -------------
    async def on_ready(self):
        self.disabled_tools = []

        # enable/disable tools based on selected modes
        if self.config.get("read-only"):
            self.disabled_tools.extend(["file_create", "file_move", "file_delete", "file_edit", "folder_delete"])

        if self.config.get("insert_sandbox_paths_into_system_prompt"):
            self.disabled_tools.append("list_sandboxes")

        # still figuring out how to best guide the AI in when to use file_inspect over file_read.
        # it's a very tough thing since most LLM's are trained to just read entire files
        # and are inclined to do so
        self.disabled_tools.append("file_outline")

    async def on_system_prompt(self):
        final_output = []

        templates = await self._get_templates()
        if templates:
            output_str = "## Templates you can read using read_template:\n"
            output_str += "\n".join([f"- {template}" for template in templates])
            final_output.append(output_str)

        if self.config.get("insert_sandbox_paths_into_system_prompt"):
            sandboxes = await self._get_sandbox_paths()
            if sandboxes:
                output_str = "## Sandboxes you have access to:\n"
                output_str += "\n".join([f"- {path}" for path in sandboxes])
                final_output.append(output_str)

            if self.config.get("add_sandbox_contents_to_sandbox_list"):
                for sandbox in sandboxes:
                    output_str = f"### Files within sandbox '{sandbox}':"
                    full_path = await self._get_full_sandbox_path(sandbox)
                    folder_list = os.listdir(full_path)

                    files = []
                    folders = []
                    for file in folder_list:
                        if os.path.isdir(os.path.join(full_path, file)):
                            folders.append(file)
                        else:
                            files.append(file)

                    folders.sort()
                    files.sort()

                    if folders:
                        output_str += "\n#### Folders:\n"
                        output_str += "\n".join([f"- {folder}" for folder in folders])
                    if files:
                        output_str += "\n#### Files:\n"
                        output_str += "\n".join([f"- {file}" for file in files])

                    final_output.append(output_str)

        if (
            "shell" in self.manager.modules
            and
            self.manager.modules["shell"].config.get("sandbox_path") not in self.config.get("sandbox_paths")
        ):
            final_output.append("NEVER run shell commands against coder sandboxes. coder sandboxes and shell sandbox are seperate.")

        if self.config.get("use_coding_prompt") and self.config.get("coding_prompt"):
            final_output.append(f"## Coding Guidelines\nYOU MUST ALWAYS follow these guidelines while using the coder:\n{self.config.get('coding_prompt')}")

        if self.config.get("read-only"):
            final_output.append("## IMPORTANT: Read-Only Mode\nYour coder module is in read-only mode and you cannot write to files. Provide output code to the user directly in your messages.")

        if final_output:
            return "\n\n".join(final_output)
        return None

    # -------------------------------
    # helper functions: sandbox stuff
    # -------------------------------
    async def _get_sandbox_paths(self):
        """
        translates the sandbox path list into basenames
        so that it can actually be used by the AI without
        having to recite full paths all the time
        """
        paths = self.config.get("sandbox_paths")
        if not paths:
            return []

        # create them if they dont exist
        for path in paths:
            os.makedirs(os.path.expanduser(path).rstrip(os.path.sep), exist_ok=True)

        # strip the paths of separators at the end so that os.path.basename doesnt return a blank string (why, python?)
        paths = [path.rstrip(os.path.sep) for path in paths]

        # now return the basename of each sandbox
        return [os.path.basename(path) for path in paths]

    async def _get_full_sandbox_path(self, requested_path: str):
        """converts a basename'd sandbox path back into the full path"""
        paths = self.config.get("sandbox_paths")
        if not paths:
            return None

        for path in paths:
            if os.path.basename(path.rstrip(os.path.sep)) == requested_path.rstrip(os.path.sep):
                full_path = os.path.abspath(os.path.expanduser(path))
                return full_path.rstrip(os.path.sep)

        raise Exception("That sandbox does not exist")

    async def _get_sandbox_subpath(self, sandbox: str, requested_path: str):
        """
        resolves a basename'd sandbox path back to its full path,
        then checks whether the requested path is within the sandbox,
        and if so, returns it
        """
        # remove the sandbox path itself from the string in case the AI decided to add it
        if requested_path == sandbox:
            requested_path = ""
        elif requested_path.startswith(sandbox + os.path.sep):
            requested_path = requested_path[len(sandbox) + 1:]

        sandbox_path = await self._get_full_sandbox_path(sandbox)
        return core.sandbox_path(sandbox_path, requested_path)

    # -----------------------------
    # helper functions: treesitter
    # -----------------------------
    async def _check_syntax(self, code: str, file_path: str):
        """verifies code for syntax errors without writing it to disk"""
        errors = []

        lang = tslp.detect_language_from_path(file_path)
        if not lang or lang in ("vimdoc", "html", "htm", "glsl"):
            # that means treesitter doesn't support the language,
            # or it's a plaintext file (labeled by treesitter as 'vimdoc'),
            # so to avoid blocking code editing for unsupported languages,
            # just pretend the syntax error check passed

            # also, html syntax is skipped because the checker is too aggressive and forbids & characters, causing tons of false positive rejections
            # the syntax checker is too aggressive for GLSL (shaders) too
            return []

        result = tslp.process(code, tslp.ProcessConfig(language=lang, diagnostics=True, structure=False))
        if not result:
            # was likely an empty file, or failed to parse
            errors.append("Failed to parse the file for syntax errors. For safety, the file was not written to disk.")
            return errors

        if result.diagnostics:
            for diag in result.diagnostics:
                errors.append(f"Line {diag.span.start_line + 1}, Col {diag.span.start_column + 1}: {diag.message}")

        # return errors if they were found, otherwise it's an empty list and callers will know there were no errors
        return errors

    async def _extract_code_structure(self, code: str, file_path: str):
        """
        uses treesitter-language-pack to extract useful information from source code
        this can then be used by the LLM to do very targeted reads of specific sections of code,
        reducing the need to read entire files into context and thus saving on token use massively

        (..but it's not done yet.)
        """
        lang = tslp.detect_language_from_path(file_path)
        if not lang:
            # return None so that the caller can handle it and tell the user
            return None

        extraction = tslp.process(code, tslp.ProcessConfig(
            language=lang,
            structure=True,
            imports=True,
            comments=False
        ))
        if not extraction:
            # was likely an empty file, or failed to parse
            return None

        data = {}
        data["symbols"] = []
        for item in extraction.structure:
            data["symbols"].append({
                "name": str(item.name),
                "kind": str(item.kind),
                "start_line": int(item.span.start_line),
                "end_line": int(item.span.end_line),
                "doc_comment": item.doc_comment,
                "signature": item.signature
            })

        if not data["symbols"]:
            # tell the AI that this is a file that must be read manually instead
            return None

        metrics = extraction.metrics
        data["metrics"] = {
            "total_lines": metrics.total_lines,
            "error_count": metrics.error_count
        }
        data["imports"] = [imprt.source for imprt in extraction.imports]

        return data

    # ---------------------------
    # helper functions: templates
    # ---------------------------
    async def _get_template_folders(self):
        template_folders = list(self.config.get("template_paths", default=[]))

        # add the internal templates path to the list of template folders
        if self.config.get("enable_builtin_templates"):
            template_folders.insert(0, self.builtin_templates_path)

        return template_folders or []

    async def _get_templates(self):
        all_templates = []
        template_folders = await self._get_template_folders()

        if not template_folders:
            return []

        for folder in template_folders:
            # resolve relative paths to the openlumara root,
            # absolute paths to their absolute locations
            folder_path = core.get_path(folder)

            try:
                templates = os.listdir(folder_path)
            except Exception as e:
                return self.result(str(e), success=False)

            all_templates.extend(templates)

        return all_templates

    # ----------------------
    # tools: file navigation
    # ----------------------
    @core.module.tool
    async def list_sandboxes(self):
        return self.result(await self._get_sandbox_paths())

    @core.module.tool
    async def glob(self, sandbox: str, pattern: str, sub_path=None, max_results: int = 200):
        """globs path for desired files. does not support regex. paths relative to sandbox root."""
        sandbox_path = await self._get_full_sandbox_path(sandbox)
        target_path = await self._get_sandbox_subpath(sandbox, sub_path or '.')

        folder_blacklist = self.config.get("folder_blacklist")

        try:
            # remove the sandbox path itself from the string in case the AI decided to add it
            if pattern == sandbox:
                pattern = ""
            elif pattern.startswith(sandbox + os.path.sep):
                pattern = pattern[len(sandbox) + 1:]

            matches = sorted(glob.glob(
                os.path.join(target_path, pattern),
                recursive=True
            ))

            results = []
            total = 0
            for match in matches:
                rel_path = os.path.relpath(match, target_path)

                # skip if any path component is in the blacklist
                path_parts = rel_path.split(os.sep)
                if any(part in folder_blacklist for part in path_parts):
                    continue

                total += 1
                if total > int(max_results):
                    break

                # ensure it's within the sandbox
                core.sandbox_path(sandbox_path, rel_path)
                results.append(rel_path)

            if total > int(max_results):
                return self.result({
                    "results": results,
                    "truncated": True,
                    "total": total,
                    "note": f"showing first {int(max_results)} of {total} matches - narrow your pattern to see more"
                })
            return self.result(results)
        except Exception as e:
            return self.result(str(e), success=False)

    @core.module.tool
    async def folder_grep(self, sandbox: str, sub_path: str, regex_pattern: str, case_sensitive=False, context: int = 0, file_extensions: list = None, max_matches: int = 30):
        """searches for regex pattern in all files in folder"""
        folder_blacklist = self.config.get("folder_blacklist")

        if regex_pattern.strip() in [".", "*"]:
            return self.result("Forbidden pattern detected. Use a more specific search!", success=False)

        # compile regex with optional case-insensitive flag
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled_pattern = regex.compile(regex_pattern, flags)

        target_path = await self._get_sandbox_subpath(sandbox, sub_path)
        if os.path.isdir(target_path):
            # recursive search
            matches = []
            for (recursive_path, folders, files) in os.walk(target_path):
                # Filter out blacklisted and hidden directories using config
                folders[:] = [d for d in folders if not d.startswith('.') and d not in folder_blacklist]

                if len(matches) >= int(max_matches):
                    break

                for file in files:
                    try:
                        filepath = os.path.join(recursive_path, file)
                        
                        # filter by extensions if specified
                        if file_extensions:
                            _, ext = os.path.splitext(file)
                            # remove dot from the extension
                            ext = ext.lstrip('.')

                            if ext not in file_extensions:
                                continue

                        with _nofollow_open(filepath, "r") as f:
                            all_lines = f.readlines()
                            for line_num, line in enumerate(all_lines, 1):
                                if compiled_pattern.search(line, timeout=self.regex_timeout):
                                    # add context lines
                                    context_lines = []
                                    start = max(0, line_num - 1 - int(context))
                                    end = min(len(all_lines), line_num + int(context))
                                    for ctx_line_num in range(start, end):
                                        if ctx_line_num + 1 != line_num:
                                            context_lines.append(all_lines[ctx_line_num].rstrip())
                                    
                                    match_dict = {
                                        "file": os.path.relpath(filepath, target_path),
                                        "line_num": line_num,
                                        "line": line.rstrip(),
                                    }
                                    if context:
                                        match_dict.update({
                                            "context_before": context_lines[:context],
                                            "context_after": context_lines[-context:] if context > 0 else []
                                        })

                                    matches.append(match_dict)
                                    if len(matches) >= int(max_matches):
                                        return self.result({
                                            "matches": matches,
                                            "note": f"Showing up to {int(max_matches)} matches. More results may be available — narrow your search pattern to see them."
                                        })
                    except Exception as e:
                        pass

            if matches:
                return self.result(matches)
            else:
                return self.result("No matches found", success=False)
        else:
            return self.result("Target path is not a folder. Grep only works on folders.", success=False)


    # ----------------------
    # tools: file management
    # ----------------------
    @core.module.tool
    async def file_create(self, sandbox: str, path: str, content: str):
        """creates new file, does not support overwriting existing files. auto-creates parent dirs in path."""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        # first, check for syntax errors
        syntax_errors = await self._check_syntax(content, target_path)
        if syntax_errors:
            return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

        # auto-create any parent folders that don't exist yet,
        # so the AI doesn't have to bother creating them manually
        parent_dir = os.path.dirname(target_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        # using try/except here instead of checking if the file exists, to defend against
        # TOCTOU (Time-Of-Check -> Time-Of-Use)
        # a race condition vulnerability that can escape sandboxes
        # am i the only one that thinks TOCTOU kinda sounds like TOC TUA aka HAWK TUAH? oh no
        try:
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(path, "x", base=root) as f:
                f.write(content)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully created. Syntax verification passed - no need to verify further.")

    @core.module.tool
    async def file_move(self, sandbox: str, orig_path: str, target_path: str):
        orig_path_sandboxed = await self._get_sandbox_subpath(sandbox, orig_path)
        target_path_sandboxed = await self._get_sandbox_subpath(sandbox, target_path)

        try:
            shutil.move(orig_path_sandboxed, target_path_sandboxed)
        except Exception as e:
            # TAWK TUAH
            return self.result(str(e), success=False)

        return self.result(f"File successfully moved: {orig_path_sandboxed} -> {target_path_sandboxed}")

    @core.module.tool
    async def file_delete(self, sandbox: str, path: str):
        """only use this if user explicitely requests it"""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        try:
            os.remove(target_path)
        except Exception as e:
            # TAWCC THUA
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully deleted")

    @core.module.tool
    async def folder_delete(self, sandbox: str, path: str):
        """only use this if user explicitely requests it. can only remove empty folders as safety precaution."""
        target_path = await self._get_sandbox_subpath(sandbox, path)
        
        try:
            os.rmdir(target_path)
        except Exception as e:
            # FAWK SHUA
            return self.result(str(e), success=False)

        return self.result(f"Folder {path} deleted")

    # ----------------------
    # tools: file reading
    # ----------------------
    @core.module.tool
    async def file_outline(self, sandbox: str, path: str):
        """provides information about source code. only works on source code files."""
        target_path = await self._get_sandbox_subpath(sandbox, path)
        try:
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(path, "r", base=root) as f:
                file_content = f.read()
                structure = await self._extract_code_structure(file_content, target_path)
                if not structure:
                    return self.result("This file could not be read by the code inspector because it is not a source code file. Use file_read instead", success=False)

                return self.result(structure)
        except Exception as e:
            # FAWK KUAH
            return self.result(str(e), success=False)

    @core.module.tool
    async def file_read(self, sandbox: str, path: str, line_start: int = None, line_end: int = None):
        """reads file, or part of file. use line_start and line_end to read in chunks."""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        # protect against tocccc touh
        try:
            content = None
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(path, "r", base=root) as f:
                content = f.read()

            if not content:
                return self.result("File was empty", success=False)
        except Exception as e:
            return self.result(str(e), success=False)

        content_lines = content.split("\n")
        total_lines = len(content_lines)

        max_lines = self.config.get("global_line_limit")

        # filesize gate
        if line_start is None and line_end is None:
            if total_lines <= max_lines:
                # Allow plain reads for small files
                line_start = 1
                line_end = total_lines
            else:
                return self.result(f"File is too large to read in full! ({total_lines} lines). Read it in chunks.", success=False)

        # default ranges
        if line_start is None:
            line_start = 1
        if line_end is None:
            line_end = -1

        # make sure it's 0-indexed
        line_start = line_start-1

        # clamp line start to above 1
        if line_start < 0:
            line_start = 1

        # change a line end of -1 to the actual last line
        if line_end == -1 or line_end > total_lines:
            line_end = total_lines
        elif line_end < 1:
            line_end = 1

        # enforce hard limit on chunk size
        hit_line_limit = line_end - line_start > max_lines
        if hit_line_limit:
            line_end = line_start + max_lines

        # now get only the requested part
        content_partial = content_lines[line_start:line_end]

        # tell the AI what got truncated
        remaining = total_lines - line_end
        truncated = remaining > 0 or hit_line_limit
        truncation_note = f"Showing lines {line_start+1}-{line_end} of {total_lines}. {remaining} lines remaining." if truncated else None
        if hit_line_limit:
            truncation_note += f" WARNING: request clamped to global line limit of {max_lines} lines"

        result = {"content": "\n".join(content_partial), "truncated": truncated}
        if truncated:
            result["truncation_note"] = truncation_note
        result["success"] = True

        return result

    @core.module.tool
    async def file_grep(self, sandbox: str, file_path: str, regex_pattern: str, case_sensitive: bool = True, context: int = 0, max_matches: int = 30):
        target_path = await self._get_sandbox_subpath(sandbox, file_path)
        
        # compile regex with optional case-insensitive flag
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled_pattern = regex.compile(regex_pattern, flags)

        try:
            matches = []
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(file_path, "r", base=root) as f:
                all_lines = f.readlines()
                for line_num, line in enumerate(all_lines, 1):
                    if compiled_pattern.search(line, timeout=self.regex_timeout):
                        # add context lines
                        context_lines = []
                        start = max(0, line_num - 1 - int(context))
                        end = min(len(all_lines), line_num + int(context))
                        for ctx_line_num in range(start, end):
                            if ctx_line_num + 1 != line_num:
                                context_lines.append(all_lines[ctx_line_num].rstrip(),)

                        match_dict = {
                            "line_num": line_num,
                            "line": line.rstrip()
                        }

                        if context:
                            match_dict.update({
                                "context_before": context_lines[:int(context)],
                                "context_after": context_lines[-int(context):] if int(context) > 0 else []
                            })

                        matches.append(match_dict)

                        if len(matches) >= int(max_matches):
                            return self.result({
                                "matches": matches,
                                "note": f"Showing up to {int(max_matches)} matches. More results may be available — narrow your search pattern to see them."
                            })

            if matches:
                return self.result(matches)
            else:
                return self.result("No matches found", success=False)
        except Exception as e:
            # FKAWK SUAH
            return self.result(str(e), success=False)

    @core.module.tool
    async def read_template(self, template_name: str):
        template_folders = await self._get_template_folders()
        if not template_folders:
            raise Exception("no template folders were configured! this should never happen, since the builtin one is always included. notify the developer!")

        for folder in template_folders:
            # resolve relative paths to the openlumara root,
            # absolute paths to their absolute locations
            folder_path = core.get_path(folder)

            try:
                templates = os.listdir(folder_path)
            except Exception as e:
                # LAWK FUAH
                return self.result(str(e), success=False)

            if template_name in templates:
                try:
                    with open(os.path.join(folder_path, template_name), 'r', encoding="utf-8") as f:
                        return self.result(f.read())
                except Exception as e:
                    # FAWK MUAH
                    return self.result(str(e), success=False)

        return self.result("Template not found!", success=False) 

    # --------------------
    # tools: file writing
    # --------------------
    @core.module.tool
    async def file_edit(self, sandbox: str, path: str, original_code: str, replacement_code: str):
       target_path = await self._get_sandbox_subpath(sandbox, path)

       file_content = None
       # protect against FAWK HUAH
       try:
           root = await self._get_full_sandbox_path(sandbox)
           with _nofollow_open(path, "r", base=root) as f:
               file_content = f.read()
       except Exception as e:
           return self.result(str(e), success=False)

       if not file_content:
           return self.result("File is empty!", success=False)

       # now do the actual replacement
       new_file_content = file_content.replace(original_code, replacement_code)

       if new_file_content == file_content:
           # that means it failed to replace!
           return self.result("Failed to match your original code string against the file contents. Try again!", success=False)

       # check for syntax errors
       syntax_errors = await self._check_syntax(new_file_content, target_path)
       if syntax_errors:
           return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

       # and write it to the file
       try:
           with _nofollow_open(path, "w", base=root) as f:
               f.write(new_file_content)
       except Exception as e:
           # TAWK TOUHA
           return self.result(str(e), success=False)

       return self.result(f"Successfully edited file {path}. Syntax verification passed - no need to verify further.")

    # ---------------------
    # user-facing commands
    # ---------------------
    @core.module.command("coder", help={
       "readonly": "toggle read-only mode"
    })
    async def cmd_coder(self, args: list):
        if len(args) == 0:
            return "please specify a sub-command (see /help coder)"

        match args[0]:
            case "readonly":
                current_state = self.config.get("read-only")
                self.config.set("read-only", not current_state)
                await self.manager.reload_module(self.name)

                if current_state:
                    return "read-only mode disabled"
                else:
                    return "read-only mode enabled"

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui extension routes for the coder sidebar (sandbox dropdown +
    # lazy file tree + edit modal). private methods are ignored by the tool
    # loader; @webui.route exposes them under /api/ext/coder/<path>.
    # saves run through the same treesitter syntax gate as coder_file_edit.

    # files the webui editor refuses to open (binary / huge)
    ui_max_read_bytes = 1_000_000

    @webui.route("sandboxes")
    async def _route_sandboxes(self, body=None, query=None):
        """sandbox names for the dropdown + whether the module is read-only.
        also carries the effective editor keybinding mode so the webui
        doesn't need its own settings endpoint (only counts when the
        umbrella extension toggle is on too)."""
        mode = self.config.get("editor_mode") or "standard"
        return {
            "sandboxes": await self._get_sandbox_paths(),
            "read_only": bool(self.config.get("read-only")),
            "editor_mode": mode if self.config.get("enable_webui_extension") else "standard",
            "autosave_interval": int(self.config.get("autosave_interval") or 0),
        }

    @webui.route("tree")
    async def _route_tree(self, body=None, query=None):
        """one directory level of a sandbox. path is relative to the sandbox
        root ('' = root). returns entries sorted folders-first."""
        sandbox = (query or {}).get("sandbox", "")
        rel_path = (query or {}).get("path", "") or ""

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        if not os.path.isdir(target):
            return self.result("not a folder", success=False)

        blacklist = self.config.get("folder_blacklist") or []
        entries = []
        try:
            for name in os.listdir(target):
                full = os.path.join(target, name)
                is_dir = os.path.isdir(full)
                child_rel = os.path.normpath(os.path.join(rel_path, name)).replace(os.sep, "/")
                entries.append({
                    "name": name,
                    "path": child_rel,
                    "is_dir": is_dir,
                    "hidden": name.startswith("."),
                    "blacklisted": is_dir and name in blacklist,
                })
        except Exception as e:
            return self.result(str(e), success=False)

        entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
        return {"path": rel_path, "entries": entries}

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    @webui.route("files")
    async def _route_files(self, body=None, query=None):
        """full recursive file list of a sandbox (relative, slash-separated)
        for the ctrl+p quick-open modal. hidden + blacklisted folders are
        skipped. deliberately UNCAPPED: os.walk is depth-first, so an early
        cap silently starved every folder that sorts after the one that ate
        the budget. the frontend caps the scored matches instead."""
        sandbox = (query or {}).get("sandbox", "")
        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            target = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        if not target or not os.path.isdir(target):
            return self.result("sandbox not found", success=False)

        blacklist = self.config.get("folder_blacklist") or []

        files = []
        try:
            for recursive_path, folders, filenames in os.walk(target):
                # prune hidden + blacklisted branches in place so os.walk
                # never descends into them (same trick folder_grep uses)
                folders[:] = [d for d in folders if not d.startswith(".") and d not in blacklist]

                for name in filenames:
                    if name.startswith("."):
                        continue
                    full = os.path.join(recursive_path, name)
                    rel = os.path.relpath(full, target).replace(os.sep, "/")
                    files.append(rel)
        except Exception as e:
            return self.result(str(e), success=False)

        files.sort()
        return {"files": files}

    @webui.route("read")
    async def _route_read(self, body=None, query=None):
        """raw text of a file, for the edit modal"""
        sandbox = (query or {}).get("sandbox", "")
        rel_path = (query or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            size = os.path.getsize(target)
            if size > self.ui_max_read_bytes:
                return self.result(f"file is too large to edit in the webui ({size} bytes)", success=False)

            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(rel_path, "r", base=root) as f:
                content = f.read()
        except UnicodeDecodeError:
            return self.result("this looks like a binary file and can't be edited here", success=False)
        except Exception as e:
            return self.result(str(e), success=False)

        return {"path": rel_path, "content": content, "read_only": bool(self.config.get("read-only"))}

    @webui.route("save", method="POST", admin_only=True)
    async def _route_save(self, body=None, query=None):
        """writes the modal's content back to disk, gated by the same
        syntax check coder_file_edit uses. refuses in read-only mode."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        content = (body or {}).get("content", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        syntax_errors = await self._check_syntax(content, target)
        if syntax_errors:
            return self.result({"errors": syntax_errors, "message": "Syntax errors detected! File was not written to disk."}, success=False)

        try:
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(rel_path, "w", base=root) as f:
                f.write(content)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"saved {rel_path}")

    @webui.route("lint", method="POST", admin_only=True)
    async def _route_lint(self, body=None, query=None):
        """live syntax annotations for the webui editor: runs the same
        treesitter check that gates saves, but returns structured results
        and never touches the disk. languages treesitter can't check
        simply come back clean, same as the save gate treats them."""
        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        content = (body or {}).get("content", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        lang = tslp.detect_language_from_path(target)
        if not lang or lang in ("vimdoc", "html", "htm"):
            return {"annotations": []}

        try:
            result = tslp.process(content, tslp.ProcessConfig(
                language=lang,
                diagnostics=True,
                structure=False,
            ))
        except Exception as e:
            return self.result(str(e), success=False)

        if not result:
            # empty file or failed to parse: stay quiet while typing,
            # the save gate is still the strict one
            return {"annotations": []}

        annotations = []
        for diag in (result.diagnostics or []):
            annotations.append({
                "line": int(diag.span.start_line) + 1,
                "col": int(diag.span.start_column) + 1,
                "end_line": int(diag.span.end_line) + 1,
                "end_col": int(diag.span.end_column) + 1,
                "message": str(diag.message),
            })

        return {"annotations": annotations}

    @webui.route("create", method="POST", admin_only=True)
    async def _route_create(self, body=None, query=None):
        """creates an empty file or a folder (webui context menu). empty
        files always pass syntax, so no treesitter gate here."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        is_dir = bool((body or {}).get("is_dir"))

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            if is_dir:
                os.makedirs(target, exist_ok=False)
            else:
                # 'x' mode: fails if the file exists, no TOCTOU
                parent = os.path.dirname(target)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                root = await self._get_full_sandbox_path(sandbox)
                with _nofollow_open(rel_path, "x", base=root) as f:
                    f.write("")
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"created {rel_path}")

    @webui.route("move", method="POST", admin_only=True)
    async def _route_move(self, body=None, query=None):
        """renames or moves an entry: src -> dst, both sandbox-relative.
        rename is just a move within the same parent."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        src = (body or {}).get("src", "")
        dst = (body or {}).get("dst", "")

        if not sandbox or not src or not dst:
            return self.result("sandbox, src and dst are all required", success=False)

        try:
            src_path = await self._get_sandbox_subpath(sandbox, src)
            dst_path = await self._get_sandbox_subpath(sandbox, dst)
        except Exception as e:
            return self.result(str(e), success=False)

        if os.path.exists(dst_path):
            return self.result(f"destination already exists: {dst}", success=False)

        try:
            parent = os.path.dirname(dst_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            shutil.move(src_path, dst_path)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"moved {src} -> {dst}")

    @webui.route("delete", method="POST", admin_only=True)
    async def _route_delete(self, body=None, query=None):
        """deletes a file, or a folder recursively. the webui confirms
        before calling this; the AI-facing tools stay stricter on purpose."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            target = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"deleted {rel_path}")

    @webui.route("duplicate", method="POST", admin_only=True)
    async def _route_duplicate(self, body=None, query=None):
        """copies a file or folder next to the original as 'name copy.ext'
        (numbered if taken)."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            src = await self._get_sandbox_subpath(sandbox, rel_path)
        except Exception as e:
            return self.result(str(e), success=False)

        if not os.path.exists(src):
            return self.result(f"not found: {rel_path}", success=False)

        parent_rel = os.path.dirname(rel_path)
        base = os.path.basename(rel_path)

        if os.path.isdir(src):
            stem, ext = base, ""
        else:
            stem, ext = os.path.splitext(base)

        n = 1
        while True:
            suffix = " copy" if n == 1 else f" copy {n}"
            new_name = stem + suffix + ext
            candidate = os.path.join(os.path.dirname(src), new_name)
            if not os.path.exists(candidate):
                break
            n += 1

        try:
            if os.path.isdir(src):
                shutil.copytree(src, candidate)
            else:
                shutil.copy2(src, candidate)
        except Exception as e:
            return self.result(str(e), success=False)

        new_rel = (parent_rel + "/" if parent_rel else "") + new_name
        return self.result(f"duplicated to {new_rel}")

    # ----------------------------
    # webui routes: sandbox search
    # ----------------------------
    @webui.route("search", method="POST")
    async def _route_search(self, body=None, query=None):
        """recursive literal (or regex) text search across a sandbox.
        skips hidden/blacklisted folders and binary/huge files, like
        folder_grep does, but returns flat results for the sidebar UI."""
        sandbox = (body or {}).get("sandbox", "")
        needle = (body or {}).get("query", "")
        use_regex = bool((body or {}).get("regex"))
        max_matches = min(int((body or {}).get("max_matches") or 200), 500)

        if not sandbox or not needle:
            return self.result("sandbox and query are both required", success=False)

        try:
            root = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        pattern = None
        if use_regex:
            try:
                pattern = regex.compile(needle, regex.IGNORECASE)
            except Exception as e:
                return self.result(f"invalid regex: {e}", success=False)

        blacklist = self.config.get("folder_blacklist") or []
        results = []
        truncated = False

        for (dirpath, dirnames, filenames) in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in blacklist]

            for fname in filenames:
                if fname.startswith("."):
                    continue

                fpath = os.path.join(dirpath, fname)
                try:
                    if os.path.getsize(fpath) > self.ui_max_read_bytes:
                        continue

                    with _nofollow_open(fpath, "r") as f:
                        for line_num, line in enumerate(f, 1):
                            if pattern:
                                try:
                                    hit = pattern.search(line, timeout=self.regex_timeout)
                                except TimeoutError:
                                    continue
                            else:
                                hit = needle.lower() in line.lower()

                            if hit:
                                results.append({
                                    "file": os.path.relpath(fpath, root).replace(os.sep, "/"),
                                    "line": line_num,
                                    "text": line.rstrip()[:300],
                                })
                                if len(results) >= max_matches:
                                    truncated = True
                                    break
                except (UnicodeDecodeError, IsADirectoryError, PermissionError, OSError):
                    continue

            if truncated:
                break

        return {"results": results, "truncated": truncated}

    # NOTE: the /files route lives up in the main webui-routes block
    # (_route_files, uncapped). there used to be a second, duplicate
    # _route_files here (3000-entry cap + truncated flag) left over from
    # scaffolding; python binds the LAST definition in a class body, so it
    # silently shadowed the real one. do not re-add one.

    # ---------------------
    # webui routes: git
    # ---------------------
    async def _run_git_bytes(self, sandbox_root: str, *args, timeout=15):
        """runs git, returns (returncode, raw stdout bytes). no text mode,
        no stripping - for output that must be parsed byte-exactly."""
        try:
            # spawn the process in a seperate thread so the entire harness process doesnt block
            proc = await asyncio.to_thread(
                subprocess.run,
                ["git", *args],
                cwd=sandbox_root,
                capture_output=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            return 127, b"git executable not found"
        except subprocess.TimeoutExpired:
            return 124, b"git command timed out"
        except Exception as e:
            return 1, str(e).encode("utf-8", "replace")

        return proc.returncode, proc.stdout or b""

    def _parse_porcelain_z(self, raw: bytes):
        """parses `git status --porcelain=v1 -z` output from raw bytes.

        VERIFIED against real git output with od -c (2026-10-13): the
        separator is a BARE NUL, and every record is exactly
        'XY<sp>path' - including codes whose first char is a space (' M').
        (the space seen after each NUL in hexdumps IS that next record's
        status code; do not 'eat' it, and do not split on NUL+space.)

        renames/copies emit 'XY<sp>oldpath' followed by a separate field
        holding the new path.

        with -z, paths are never quoted and never mangled. returns a list
        of dicts: path / xy / staged / untracked."""

        def decode(data: bytes) -> str:
            return data.decode("utf-8", "replace").replace(os.sep, "/")

        fields = raw.split(b"\x00")

        entries = []
        idx = 0
        while idx < len(fields):
            field = fields[idx]
            idx += 1

            if not field:
                # empty piece after the trailing NUL
                continue

            if len(field) < 3 or field[2:3] != b" ":
                # not 'XY path' - malformed for us, skip rather than guess
                continue

            x = chr(field[0])
            y = chr(field[1])
            path = decode(field[3:])

            if x in ("R", "C") or y in ("R", "C"):
                # next field is the NEW path (kept); consume it either way
                if idx < len(fields):
                    newp = fields[idx]
                    idx += 1
                    if newp:
                        path = decode(newp)

            entries.append({
                "path": path,
                "xy": x + y,
                "staged": x not in (" ", "?"),
                "untracked": x == "?" and y == "?",
            })

        return entries

    async def _run_git(self, sandbox_root: str, *args, accept=(0,), timeout=15):
        """runs git in the sandbox root. returns (ok, output).
        accept lists return codes that count as success."""
        try:
            # spawn git in a seperate thread
            proc = await asyncio.to_thread(
                subprocess.run,
                ["git", *args],
                cwd=sandbox_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            return False, "git executable not found"
        except subprocess.TimeoutExpired:
            return False, "git command timed out"
        except Exception as e:
            return False, str(e)

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()

        if proc.returncode not in accept:
            return False, (err or out or f"git {args[0] if args else ''} failed (code {proc.returncode})")

        return True, (out or err)

    async def _git_root(self, sandbox: str, subpath: str = ""):
        """resolves sandbox + optional subpath (sandbox-relative) into the
        folder git should run in. lets git work on repos nested inside a
        sandbox, e.g. 'openlumara_dev' within the 'dev' sandbox."""
        full = await self._get_full_sandbox_path(sandbox)
        if not subpath:
            return full
        return core.sandbox_path(full, subpath)

    def _check_git_paths(self, root: str, paths: list):
        """ensures repo-relative paths passed to git resolve inside THE
        REPOSITORY itself."""
        root = os.path.normpath(root)
        for p in paths:
            full = os.path.normpath(os.path.join(root, p))
            if full != root and not full.startswith(root + os.sep):
                raise Exception(f"path escapes the repository: {p}")

    @webui.route("git_repos")
    async def _route_git_repos(self, body=None, query=None):
        """lists git repositories inside a sandbox: the sandbox root itself
        if it is one, plus nested repos up to 4 folder levels deep. once a
        repo is found its subtree is skipped, so the list stays shallow."""
        sandbox = (query or {}).get("sandbox", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._get_full_sandbox_path(sandbox)
        except Exception as e:
            return self.result(str(e), success=False)

        blacklist = self.config.get("folder_blacklist") or []
        max_depth = 6
        max_repos = 50

        repos = []

        def is_repo(path):
            return os.path.isdir(os.path.join(path, ".git")) or os.path.isfile(os.path.join(path, ".git"))

        if is_repo(root):
            repos.append("")

        for (dirpath, dirnames, filenames) in os.walk(root):
            rel = os.path.relpath(dirpath, root).replace(os.sep, "/")
            depth = 0 if rel == "." else len(rel.split("/"))

            # prune hidden + blacklisted folders, and anything too deep
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in blacklist and depth + 1 <= max_depth]

            if depth == 0 or depth > max_depth:
                continue

            if is_repo(dirpath):
                repos.append(rel)
                dirnames[:] = []  # skip the repo's own subtree
                if len(repos) >= max_repos:
                    break

        return {"repos": repos}

    @webui.route("git_status")
    async def _route_git_status(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, _ = await self._run_git(root, "rev-parse", "--is-inside-work-tree")
        if not ok:
            return {"is_repo": False, "read_only": bool(self.config.get("read-only"))}

        _, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")

        ok_b, b_out = await self._run_git(root, "branch", "--format=%(refname:short)")
        branches = [b.strip() for b in b_out.split("\n") if b.strip()] if ok_b else []

        # nul-delimited porcelain, parsed from raw bytes (no text mode,
        # no stripping) by a dedicated parser with explicit separator
        # handling. see _parse_porcelain_z for the exact byte format.
        rc_s, raw_s = await self._run_git_bytes(root, "status", "--porcelain=v1", "-z")
        changes = self._parse_porcelain_z(raw_s) if rc_s == 0 else []

        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        # keep-committed mode (setting git_keep_committed_visible): files
        # that sit in unpushed commits stay in the list marked 'committed'
        # instead of vanishing on commit; they leave when a push ships them.
        # committed+still-dirty files keep their working-tree entry and just
        # gain the committed flag. base resolution is fully server side.
        keep = bool(self.config.get("git_keep_committed_visible"))
        committed = {}
        if keep:
            base, _target, _note = await self._git_pending_base(root)
            if base:
                rc_n, raw_n = await self._run_git_bytes(root, "diff", "--numstat", "--no-renames", f"{base}..HEAD")
                if rc_n == 0:
                    for line in raw_n.decode("utf-8", "replace").splitlines():
                        parts = line.split("\t", 2)
                        if len(parts) < 3:
                            continue
                        committed[parts[2].replace(os.sep, "/")] = True
        # a dirty file whose path is in an unpushed commit appears TWICE:
        # once in the active group (its working-tree state, with a purple
        # ring) and once in the pinned bottom group as committed_only - the
        # violet row is the entry point to the COMMIT diff (git_pending_diff),
        # which the working-tree diff cannot show. also_dirty lets the UI
        # label that combo in the tooltip.
        dirty_paths = {c["path"] for c in changes}
        for c in changes:
            c["committed"] = c["path"] in committed
        for p in sorted(committed):
            changes.append({
                "path": p, "xy": "C ", "staged": False, "untracked": False,
                "committed": True, "committed_only": True,
                "also_dirty": p in dirty_paths,
            })

        # last commit (hash + subject) so the sidebar can offer an amend
        # toggle without a second round-trip to git_log
        last_commit = {"hash": "", "msg": ""}
        ok_l, out_l = await self._run_git(root, "log", "-n1", "--pretty=%h%x09%s")
        if ok_l and out_l.strip():
            h, _, m = out_l.strip().partition("\t")
            last_commit = {"hash": h, "msg": m}

        return {
            "is_repo": True,
            "branch": branch,
            "branches": branches,
            "changes": changes,
            "read_only": bool(self.config.get("read-only")),
            "keep_committed": keep,
            "last_commit": last_commit,
        }

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # lightweight recent-commit peek for the welcome card's git strip.
    # same %h + %s fields (and tab-split parsing) as git_log, just capped:
    # the strip never needs more than a handful of rows.
    @webui.route("git_recent")
    async def _route_git_recent(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        limit = min(int((query or {}).get("n", 5)), 20)

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, _ = await self._run_git(root, "rev-parse", "--is-inside-work-tree")
        if not ok:
            return {"is_repo": False}

        _, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")

        rc, raw = await self._run_git_bytes(
            root, "log", f"--pretty=%h%x09%s", f"-n{limit}"
        )
        if rc != 0:
            # a repo without any commits yet is not an error worth surfacing
            return {"is_repo": True, "branch": branch, "log": []}

        entries = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                h, msg = line.split("\t", 1)
            else:
                h, msg = line, ""
            entries.append({"hash": h.strip(), "msg": msg})

        return {"is_repo": True, "branch": branch, "log": entries}

    @webui.route("git_stage", method="POST", admin_only=True)
    async def _route_git_stage(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        paths = (body or {}).get("paths", [])

        if not sandbox or not paths:
            return self.result("sandbox and paths are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, paths)
            abs_paths = [os.path.normpath(os.path.join(root, p)) for p in paths]
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "add", "--", *abs_paths)
        if not ok:
            return self.result(out, success=False)

        return self.result("staged")

    @webui.route("git_unstage", method="POST", admin_only=True)
    async def _route_git_unstage(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        paths = (body or {}).get("paths", [])

        if not sandbox or not paths:
            return self.result("sandbox and paths are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, paths)
            abs_paths = [os.path.normpath(os.path.join(root, p)) for p in paths]
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "restore", "--staged", "--", *abs_paths)
        if not ok:
            return self.result(out, success=False)

        return self.result("unstaged")

    @webui.route("git_commit", method="POST", admin_only=True)
    async def _route_git_commit(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        message = (body or {}).get("message", "").strip()
        # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
        # amend mode: fold the staged changes (and/or a new message) into
        # HEAD instead of creating a new commit. empty message = --no-edit.
        amend = bool((body or {}).get("amend"))

        if not sandbox or (not amend and not message):
            return self.result("sandbox and message are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        if amend:
            # never rewrite published history: HEAD itself must still be
            # unpushed. base == HEAD means the remote already has the exact
            # commit we would be rewriting -> refuse. no resolvable base
            # (fresh branch / detached) -> nothing can have shipped from it,
            # except detached HEAD where amending is pointless -> also refuse.
            ok_h, head = await self._run_git(root, "rev-parse", "HEAD")
            if not ok_h or not head.strip():
                return self.result("nothing to amend: this repository has no commits yet", success=False)
            head = head.strip()
            base, target, note = await self._git_pending_base(root)
            if "detached" in (note or ""):
                return self.result("cannot amend on a detached HEAD", success=False)
            if base and base == head:
                return self.result(
                    f"the latest commit is already pushed to {target}: amending it would rewrite published history",
                    success=False,
                )
            if message:
                ok, out = await self._run_git(root, "commit", "--amend", "-m", message)
            else:
                ok, out = await self._run_git(root, "commit", "--amend", "--no-edit")
            if not ok:
                return self.result(out, success=False)
            return self.result(out)

        ok, out = await self._run_git(root, "commit", "-m", message)
        if not ok:
            return self.result(out, success=False)

        return self.result(out)

    @webui.route("git_branch", method="POST", admin_only=True)
    async def _route_git_branch(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        name = (body or {}).get("name", "").strip()

        if not sandbox or not name:
            return self.result("sandbox and name are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, out = await self._run_git(root, "switch", name)
        if not ok:
            return self.result(out, success=False)

        return self.result(out or f"switched to {name}")

    @webui.route("git_ahead")
    async def _route_git_ahead(self, body=None, query=None):
        """what a push would send: the unpushed commits, the target ref and
        the warnings (behind/diverged, dirty tree). the push confirmation
        modal is built entirely from this payload."""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            return self.result(branch, success=False)
        if branch == "HEAD":
            return self.result("detached HEAD: switch to a branch before pushing", success=False)

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return self.result("this repo has no remotes, nowhere to push to", success=False)
        remote = "origin" if "origin" in remotes else remotes[0]

        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        upstream = upstream.strip() if ok else ""
        has_upstream = "/" in upstream

        if has_upstream:
            target = upstream
            # NOTE: _run_git_bytes returns (returncode, raw) NOT (ok, out) -
            # check rc != 0, never `if not ok` (0 means success!).
            rc, raw = await self._run_git_bytes(
                root, "log", "--pretty=%h%x09%s", f"{upstream}..HEAD", "-n100"
            )
        else:
            # brand new branch: commits that exist on no remote at all
            target = f"{remote}/{branch}"
            rc, raw = await self._run_git_bytes(
                root, "log", "--pretty=%h%x09%s", "HEAD", "--not", "--remotes", "-n100"
            )

        if rc != 0:
            return self.result(raw.decode("utf-8", "replace").strip() or "git log failed", success=False)

        ahead = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                h, msg = line.split("\t", 1)
            else:
                h, msg = line, ""
            ahead.append({"hash": h.strip(), "msg": msg})

        behind = 0
        if has_upstream:
            ok, out = await self._run_git(root, "rev-list", "--count", f"HEAD..{upstream}")
            if ok and out.strip().isdigit():
                behind = int(out.strip())

        _, raw = await self._run_git_bytes(root, "status", "--porcelain=v1")
        dirty = bool(raw.strip())

        return {
            "branch": branch,
            "remote": remote,
            "upstream": upstream,
            "has_upstream": has_upstream,
            "target": target,
            "ahead": ahead,
            "behind": behind,
            "dirty": dirty,
        }

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-23) harness:openlumara
    # 'review what a push would send': the push modal lists commits already,
    # but a push ships CODE, not commit messages. these routes expose the
    # file list + diff between the remote base and HEAD, resolved entirely
    # server side (the client never supplies a revision, so there is nothing
    # to inject).
    async def _git_pending_base(self, root):
        """resolve the diff base for a pending push.
        returns (base_sha | None, target_desc, note)."""
        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok or branch.strip() == "HEAD":
            return None, "", "detached HEAD: nothing to review"

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return None, "", "this repo has no remotes"
        remote = "origin" if "origin" in remotes else remotes[0]

        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        upstream = upstream.strip() if ok else ""
        if "/" in upstream:
            ok, sha = await self._run_git(root, "rev-parse", upstream)
            if not ok:
                return None, upstream, f"could not resolve {upstream} - has it ever been fetched?"
            return sha.strip(), upstream, ""

        # brand new branch: compare against the closest remote history found
        for cand in (f"{remote}/HEAD", f"{remote}/main", f"{remote}/master"):
            ok, out = await self._run_git(root, "rev-parse", "--verify", "--quiet", cand)
            if ok and out.strip():
                ok, out = await self._run_git(root, "merge-base", "HEAD", cand)
                if ok and out.strip():
                    return out.strip(), f"{remote}/{branch.strip()} (new branch)", ""
        return None, f"{remote}/{branch.strip()} (new branch)", "no comparable remote history found: this push publishes everything on the branch"

    @webui.route("git_pending_files")
    async def _route_git_pending_files(self, body=None, query=None):
        """files (and line counts) that a push would transfer"""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        base, target, note = await self._git_pending_base(root)
        if base is None:
            return {"files": [], "target": target, "note": note}

        rc, raw = await self._run_git_bytes(root, "diff", "--numstat", "--no-renames", f"{base}..HEAD")
        if rc != 0:
            return self.result(raw.decode("utf-8", "replace").strip() or "git diff failed", success=False)

        files = []
        for line in raw.decode("utf-8", "replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            # added/removed are '-' for binary files: pass through as-is
            files.append({"path": parts[2], "added": parts[0], "removed": parts[1]})
        return {"files": files, "target": target, "note": ""}

    @webui.route("git_pending_diff")
    async def _route_git_pending_diff(self, body=None, query=None):
        """unified + split diff for one file, between the remote base and HEAD"""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        rel_path = (query or {}).get("path", "")
        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        base, target, note = await self._git_pending_base(root)
        if base is None:
            return self.result(note or "no comparable remote history to diff against", success=False)

        abs_path = os.path.normpath(os.path.join(root, rel_path))
        rc, raw = await self._run_git_bytes(root, "diff", f"{base}..HEAD", "--", abs_path)
        if rc not in (0, 1):
            return self.result(raw.decode("utf-8", "replace").strip() or "git diff failed", success=False)

        text = raw.decode("utf-8", "replace")
        return {"diff": text, "rows": self._parse_split_diff(text), "target": target}

    @webui.route("git_push", method="POST", admin_only=True)
    async def _route_git_push(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        # everything is re-checked server side: the modal's confirmation
        # button is human intent, not a security boundary.
        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok or branch == "HEAD":
            return self.result("detached HEAD: switch to a branch before pushing", success=False)

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return self.result("this repo has no remotes, nowhere to push to", success=False)
        remote = "origin" if "origin" in remotes else remotes[0]

        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        upstream = upstream.strip() if ok else ""

        # explicit refspec so a weird push.default config can never widen
        # the push to other branches. never --force: without it git itself
        # rejects anything that isn't a fast-forward.
        if "/" in upstream:
            up_remote, _, up_branch = upstream.partition("/")
            args = ["push", up_remote, f"{branch}:{up_branch}"]
        else:
            args = ["push", "-u", remote, branch]

        # pushes can be slow on big repos or bad connections
        rc, raw = await self._run_git_bytes(root, *args, timeout=180)
        out = raw.decode("utf-8", "replace").strip()
        if rc != 0:
            return self.result(out or "git push failed", success=False)

        return self.result(out or "pushed")

    @webui.route("git_log")
    async def _route_git_log(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        limit = min(int((query or {}).get("n", 20)), 100)

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        # %x09 = literal tab: hash and subject are split on the one
        # character a short hash can never contain. parsed from raw bytes.
        rc, raw = await self._run_git_bytes(
            root, "log", f"--pretty=%h%x09%s", f"-n{limit}"
        )
        if rc != 0:
            return self.result(raw.decode("utf-8", "replace").strip() or "git log failed", success=False)

        entries = []
        for line in raw.decode("utf-8", "replace").splitlines():
            if not line.strip():
                continue
            if "\t" in line:
                h, msg = line.split("\t", 1)
            else:
                h, msg = line, ""
            entries.append({"hash": h.strip(), "msg": msg})

        return {"log": entries}

    @webui.route("git_diff")
    async def _route_git_diff(self, body=None, query=None):
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        rel_path = (query or {}).get("path", "")
        staged = (query or {}).get("staged", "") in ("1", "true")
        untracked = (query or {}).get("untracked", "") in ("1", "true")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        # absolute pathspec: git resolves relative ones against the cwd,
        # which only matches the repo-root-relative porcelain paths when
        # the repo happens to BE the sandbox root. absolute works from any
        # cwd, so nested repos stage/unstage/diff the right file.
        abs_path = os.path.normpath(os.path.join(root, rel_path))

        if untracked:
            # no-index exits 1 when there IS a diff: accept both codes
            rc, raw = await self._run_git_bytes(
                root, "diff", "--no-index", "--", os.devnull, abs_path
            )
            ok = rc in (0, 1)
        elif staged:
            rc, raw = await self._run_git_bytes(root, "diff", "--staged", "--", abs_path)
            ok = rc == 0
        else:
            rc, raw = await self._run_git_bytes(root, "diff", "--", abs_path)
            ok = rc == 0

        if not ok:
            return self.result(raw.decode("utf-8", "replace").strip() or f"git diff failed (code {rc})", success=False)

        text = raw.decode("utf-8", "replace")
        return {"diff": text if text.strip() else "(no changes)"}

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui routes: git fetch + pull
    # ------------------------------
    @webui.route("git_fetch", method="POST", admin_only=True)
    async def _route_git_fetch(self, body=None, query=None):
        """fetches from remote without merging. returns incoming commits."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok:
            return self.result(branch, success=False)

        ok, out = await self._run_git(root, "remote")
        remotes = out.split() if ok else []
        if not remotes:
            return self.result("this repo has no remotes", success=False)
        remote = "origin" if "origin" in remotes else remotes[0]

        rc, raw = await self._run_git_bytes(root, "fetch", remote, "--prune", timeout=120)
        out = raw.decode("utf-8", "replace").strip()
        if rc != 0:
            return self.result(out or "git fetch failed", success=False)

        # what's incoming after fetch
        ok, upstream = await self._run_git(root, "rev-parse", "--abbrev-ref", "@{u}")
        incoming = []
        if ok and "/" in upstream.strip():
            rc2, raw2 = await self._run_git_bytes(
                root, "log", "--pretty=%h%x09%s", f"HEAD..{upstream.strip()}", "-n100"
            )
            if rc2 == 0:
                for line in raw2.decode("utf-8", "replace").splitlines():
                    if not line.strip():
                        continue
                    if "\t" in line:
                        h, msg = line.split("\t", 1)
                    else:
                        h, msg = line, ""
                    incoming.append({"hash": h.strip(), "msg": msg})

        return {"output": out, "incoming": incoming, "branch": branch}

    @webui.route("git_pull", method="POST", admin_only=True)
    async def _route_git_pull(self, body=None, query=None):
        """pulls from remote. returns output or conflict info."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        ok, branch = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if not ok or branch == "HEAD":
            return self.result("detached HEAD: switch to a branch before pulling", success=False)

        rc, raw = await self._run_git_bytes(root, "pull", timeout=120)
        out = raw.decode("utf-8", "replace").strip()

        if rc != 0:
            # check if there are conflicts
            _, conflict_raw = await self._run_git_bytes(root, "diff", "--name-only", "--diff-filter=U")
            conflicts = [l for l in conflict_raw.decode("utf-8", "replace").splitlines() if l.strip()]
            if conflicts:
                return {"conflicts": conflicts, "output": out, "pull_failed": True}
            return self.result(out or "git pull failed", success=False)

        return self.result(out or "pulled")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui routes: branch create / delete
    # -------------------------------------
    @webui.route("git_branch_create", method="POST", admin_only=True)
    async def _route_git_branch_create(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        name = (body or {}).get("name", "").strip()
        checkout = bool((body or {}).get("checkout", True))

        if not sandbox or not name:
            return self.result("sandbox and name are both required", success=False)

        # basic branch name validation
        if not regex.match(r"^[a-zA-Z0-9._/\-]+$", name):
            return self.result("invalid branch name: use letters, digits, dots, slashes, hyphens, underscores", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        if checkout:
            ok, out = await self._run_git(root, "switch", "-c", name)
        else:
            ok, out = await self._run_git(root, "branch", name)
        if not ok:
            return self.result(out, success=False)

        return self.result(out or f"created branch {name}")

    @webui.route("git_branch_delete", method="POST", admin_only=True)
    async def _route_git_branch_delete(self, body=None, query=None):
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        name = (body or {}).get("name", "").strip()
        force = bool((body or {}).get("force", False))

        if not sandbox or not name:
            return self.result("sandbox and name are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        # refuse to delete the current branch
        _, current = await self._run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
        if current.strip() == name:
            return self.result("cannot delete the branch you are currently on", success=False)

        args = ["branch", "-D" if force else "-d", name]
        ok, out = await self._run_git(root, *args)
        if not ok:
            return self.result(out, success=False)

        return self.result(out or f"deleted branch {name}")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui routes: conflict detection + resolution
    # -----------------------------------------------
    @webui.route("git_conflicts")
    async def _route_git_conflicts(self, body=None, query=None):
        """lists files with merge conflicts."""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")

        if not sandbox:
            return self.result("no sandbox given", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
        except Exception as e:
            return self.result(str(e), success=False)

        rc, raw = await self._run_git_bytes(root, "diff", "--name-only", "--diff-filter=U")
        if rc != 0:
            return {"conflicts": []}

        conflicts = [l.strip() for l in raw.decode("utf-8", "replace").splitlines() if l.strip()]
        return {"conflicts": conflicts}

    @webui.route("git_resolve", method="POST", admin_only=True)
    async def _route_git_resolve(self, body=None, query=None):
        """resolves a conflicted file: strategy is 'ours', 'theirs', or 'both'."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        rel_path = (body or {}).get("path", "")
        strategy = (body or {}).get("strategy", "ours")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)
        if strategy not in ("ours", "theirs", "both"):
            return self.result("strategy must be 'ours', 'theirs', or 'both'", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        if strategy == "ours":
            ok, out = await self._run_git(root, "checkout", "--ours", "--", rel_path)
        elif strategy == "theirs":
            ok, out = await self._run_git(root, "checkout", "--theirs", "--", rel_path)
        else:
            # "both": concatenate both sides without conflict markers
            abs_path = os.path.normpath(os.path.join(root, rel_path))
            try:
                with _nofollow_open(rel_path, "r", base=root) as f:
                    content = f.read()
                # strip conflict markers, keep both sides
                resolved = regex.sub(
                    r"<<<<<<< [^\n]*\n(.*?)=======\n(.*?)>>>>>>> [^\n]*\n",
                    lambda m: m.group(1) + m.group(2),
                    content,
                    flags=regex.DOTALL,
                )
                with _nofollow_open(rel_path, "w", base=root) as f:
                    f.write(resolved)
                ok = True
                out = "resolved (both)"
            except Exception as e:
                ok = False
                out = str(e)

        if not ok:
            return self.result(out, success=False)

        # stage the resolved file
        abs_path = os.path.normpath(os.path.join(root, rel_path))
        await self._run_git(root, "add", "--", abs_path)

        return self.result(f"resolved {rel_path} ({strategy})")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui route: revert a file to HEAD
    # ------------------------------------
    @webui.route("git_revert_file", method="POST", admin_only=True)
    async def _route_git_revert_file(self, body=None, query=None):
        """restores a file to its HEAD version, discarding all local
        modifications (staged and unstaged). the webui confirms before
        calling this."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        subpath = (body or {}).get("subpath", "")
        rel_path = (body or {}).get("path", "")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        abs_path = os.path.normpath(os.path.join(root, rel_path))

        # restore from HEAD (works for both tracked-modified and staged-modified)
        ok, out = await self._run_git(root, "restore", "--source=HEAD", "--staged", "--worktree", "--", abs_path)
        if not ok:
            return self.result(out, success=False)

        return self.result(f"reverted {rel_path} to HEAD")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui route: file upload (drag from OS into tree)
    # ---------------------------------------------------
    @webui.route("upload", method="POST", admin_only=True)
    async def _route_upload(self, body=None, query=None):
        """writes a file from a base64-encoded payload into the sandbox.
        used by the webui's drag-and-drop-from-OS upload. auto-creates
        parent dirs. refuses if the target already exists."""
        if self.config.get("read-only"):
            return self.result("coder is in read-only mode", success=False)

        sandbox = (body or {}).get("sandbox", "")
        rel_path = (body or {}).get("path", "")
        content_b64 = (body or {}).get("content", "")
        filename = (body or {}).get("filename", "")

        if not sandbox or not rel_path or not filename:
            return self.result("sandbox, path and filename are all required", success=False)

        # sanitize filename: strip path separators
        safe_name = regex.sub(r"[/\\]", "_", filename)
        target_rel = rel_path.rstrip("/") + "/" + safe_name if rel_path else safe_name

        try:
            target = await self._get_sandbox_subpath(sandbox, target_rel)
        except Exception as e:
            return self.result(str(e), success=False)

        if os.path.exists(target):
            return self.result(f"file already exists: {target_rel}", success=False)

        # decode base64
        import base64
        try:
            raw = base64.b64decode(content_b64)
        except Exception:
            return self.result("invalid base64 content", success=False)

        # size guard: 10MB max
        if len(raw) > 10_000_000:
            return self.result("file too large (max 10MB)", success=False)

        try:
            parent = os.path.dirname(target)
            if parent:
                os.makedirs(parent, exist_ok=True)
            root = await self._get_full_sandbox_path(sandbox)
            with _nofollow_open(target_rel, "wb", base=root) as f:
                f.write(raw)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"uploaded {target_rel}")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: 2026-10-13
    # webui route: split diff (side-by-side data)
    # ---------------------------------------------
    @webui.route("git_split_diff")
    async def _route_git_split_diff(self, body=None, query=None):
        """returns structured side-by-side diff data for the split view.
        each row: { old_num, old_text, new_num, new_text, type }
        type: 'equal', 'add', 'del', 'mod'"""
        sandbox = (query or {}).get("sandbox", "")
        subpath = (query or {}).get("subpath", "")
        rel_path = (query or {}).get("path", "")
        staged = (query or {}).get("staged", "") in ("1", "true")
        untracked = (query or {}).get("untracked", "") in ("1", "true")

        if not sandbox or not rel_path:
            return self.result("sandbox and path are both required", success=False)

        try:
            root = await self._git_root(sandbox, subpath)
            self._check_git_paths(root, [rel_path])
        except Exception as e:
            return self.result(str(e), success=False)

        abs_path = os.path.normpath(os.path.join(root, rel_path))

        # get unified diff, then parse into side-by-side rows
        if untracked:
            rc, raw = await self._run_git_bytes(
                root, "diff", "--no-index", "--", os.devnull, abs_path
            )
        elif staged:
            rc, raw = await self._run_git_bytes(root, "diff", "--staged", "--", abs_path)
        else:
            rc, raw = await self._run_git_bytes(root, "diff", "--", abs_path)

        if rc not in (0, 1):
            return self.result(raw.decode("utf-8", "replace").strip() or "git diff failed", success=False)

        text = raw.decode("utf-8", "replace")
        rows = self._parse_split_diff(text)
        return {"rows": rows}

    def _parse_split_diff(self, unified_text):
        """parses unified diff into side-by-side rows."""
        rows = []
        old_line = 0
        new_line = 0
        del_buffer = []
        add_buffer = []

        def flush_buffers():
            nonlocal del_buffer, add_buffer
            # pair up dels and adds as 'mod' rows
            while del_buffer and add_buffer:
                d = del_buffer.pop(0)
                a = add_buffer.pop(0)
                rows.append({
                    "old_num": d[0], "old_text": d[1],
                    "new_num": a[0], "new_text": a[1],
                    "type": "mod",
                })
            # leftovers are pure del or add
            for d in del_buffer:
                rows.append({"old_num": d[0], "old_text": d[1], "new_num": None, "new_text": None, "type": "del"})
            for a in add_buffer:
                rows.append({"old_num": None, "old_text": None, "new_num": a[0], "new_text": a[1], "type": "add"})
            del_buffer = []
            add_buffer = []

        for line in unified_text.split("\n"):
            hunk = regex.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if hunk:
                flush_buffers()
                old_line = int(hunk.group(1))
                new_line = int(hunk.group(2))
                continue

            if line.startswith("---") or line.startswith("+++") or line.startswith("\\"):
                continue

            if line.startswith("-"):
                flush_buffers() if add_buffer else None
                del_buffer.append((old_line, line[1:]))
                old_line += 1
            elif line.startswith("+"):
                add_buffer.append((new_line, line[1:]))
                new_line += 1
            elif line.startswith(" "):
                flush_buffers()
                rows.append({
                    "old_num": old_line, "old_text": line[1:],
                    "new_num": new_line, "new_text": line[1:],
                    "type": "equal",
                })
                old_line += 1
                new_line += 1

        flush_buffers()
        return rows

    def on_tool_summary(self, name, args, response):
        match name:
            case "coder_file_edit":
                if not isinstance(response, dict) or response.get("status") != "success":
                    return ""
                
                original = args.get("original_code") or ""
                replacement = args.get("replacement_code") or ""
                if not original or not replacement:
                    return ""
                
                added = deleted = 0
                matcher = difflib.SequenceMatcher(
                    None, original.splitlines(), replacement.splitlines()
                )
                
                for op, i1, i2, j1, j2 in matcher.get_opcodes():
                    if op in ("insert", "replace"):
                        added += j2 - j1
                    if op in ("delete", "replace"):
                        deleted += i2 - i1
                        
                return f"+{added} \u2212{deleted}"

            case "coder_file_read":
                if not isinstance(response, dict) or response.get("status") == "error":
                    return ""
                
                content = response.get("content")
                if not isinstance(content, str):
                    return ""
                
                n = len(content.split("\n"))
                return f"{n} line" + ("" if n == 1 else "s")

            case "coder_file_create":
                if not isinstance(response, dict) or response.get("status") != "success":
                    return ""
                
                content = args.get("content") or ""
                if not content:
                    return ""
                
                if content.endswith("\n"):
                    content = content[:-1]
                    
                n = len(content.split("\n"))
                return f"{n} line" + ("" if n == 1 else "s")

            case "coder_folder_grep" | "coder_file_grep":
                if not isinstance(response, dict) or response.get("status") != "success":
                    return ""
                
                c = response.get("content")
                if isinstance(c, list):
                    items = c
                elif isinstance(c, dict) and isinstance(c.get("matches"), list):
                    items = c["matches"]
                else:
                    items = []
                    
                fallback = args.get("file_path")
                if fallback is None:
                    fallback = args.get("sub_path")
                if fallback is None:
                    fallback = "matches"
                    
                files = set()
                n = 0
                for m in items:
                    if not isinstance(m, dict):
                        continue
                    files.add(m.get("file") or fallback)
                    n += 1
                    
                if not n:
                    return ""
                if len(files) > 1:
                    return f"{n} matches \u00b7 {len(files)} files"
                
                return f"{n} match" + ("" if n == 1 else "es")

            case "coder_glob":
                if not isinstance(response, dict) or response.get("status") != "success":
                    return ""
                
                c = response.get("content")
                if isinstance(c, list):
                    items = c
                elif isinstance(c, dict) and isinstance(c.get("results"), list):
                    items = c["results"]
                else:
                    items = []
                    
                n = sum(1 for f in items if isinstance(f, str))
                if not n:
                    return ""
                
                return f"{n} file" + ("" if n == 1 else "s")

        return ""
