import core
import os
import importlib
import shutil
import regex
import glob
import fnmatch
import tree_sitter_language_pack as tslp

class Coder(core.module.Module):
    """Lets your AI write code within sandboxes, without using a shell. Validates code syntax before writing to disk to protect your code from breaking."""

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
            "default": ["~/coder"],
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
                return os.path.expanduser(path).rstrip(os.path.sep)

        raise Exception("That sandbox does not exist")

    async def _get_sandbox_subpath(self, sandbox: str, requested_path: str):
        """
        resolves a basename'd sandbox path back to its full path,
        then checks whether the requested path is within the sandbox,
        and if so, returns it
        """
        # remove the sandbox path itself from the string in case the AI decided to add it
        if requested_path.startswith(sandbox):
            requested_path = requested_path[len(sandbox):]

        sandbox_path = await self._get_full_sandbox_path(sandbox)
        return core.sandbox_path(sandbox_path, requested_path)

    # -----------------------------
    # helper functions: treesitter
    # -----------------------------
    async def _check_syntax(self, code: str, file_path: str):
        """verifies code for syntax errors without writing it to disk"""
        errors = []

        lang = tslp.detect_language_from_path(file_path)
        if not lang or lang in ("vimdoc", "html", "htm"):
            # that means treesitter doesn't support the language,
            # or it's a plaintext file (labeled by treesitter as 'vimdoc'),
            # so to avoid blocking code editing for unsupported languages,
            # just pretend the syntax error check passed

            # also, html syntax is skipped because the checker is too aggressive and forbids & characters, causing tons of false positive rejections
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
    async def list_sandboxes(self):
        return self.result(await self._get_sandbox_paths())

    async def glob(self, sandbox: str, pattern: str, sub_path=None, recursive: bool = False, max_results: int = 200):
        """globs path for desired files. does not support regex. paths relative to sandbox root."""
        sandbox_path = await self._get_full_sandbox_path(sandbox)
        target_path = await self._get_sandbox_subpath(sandbox, sub_path or '.')

        folder_blacklist = self.config.get("folder_blacklist")

        try:
            # remove the sandbox path itself from the string in case the AI decided to add it
            if pattern.startswith(sandbox):
                pattern = pattern[len(sandbox):]

            # if the pattern doesn't contain **, prefix with **/ for recursive matching
            if recursive:
                if '**' not in pattern and '/' not in pattern:
                    pattern = f"**/{pattern}"
                elif '/' in pattern and '**' not in pattern:
                    pattern = f"**/{pattern}"

            matches = sorted(glob.glob(
                os.path.join(target_path, pattern),
                recursive=recursive
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
                            if ext[1:] not in file_extensions:
                                continue

                        with open(filepath, 'r', encoding="utf-8") as f:
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
    async def file_create(self, sandbox: str, path: str, content: str):
        """creates new file. auto-creates parent dirs in path"""
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
            with open(target_path, 'x') as f:
                f.write(content)
        except Exception as e:
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully created")

    async def file_move(self, sandbox: str, orig_path: str, target_path: str):
        orig_path_sandboxed = await self._get_sandbox_subpath(sandbox, orig_path)
        target_path_sandboxed = await self._get_sandbox_subpath(sandbox, target_path)

        try:
            shutil.move(orig_path_sandboxed, target_path_sandboxed)
        except Exception as e:
            # TAWK TUAH
            return self.result(str(e), success=False)

        return self.result(f"File successfully moved: {orig_path_sandboxed} -> {target_path_sandboxed}")

    async def file_delete(self, sandbox: str, path: str):
        """only use this if user explicitely requests it"""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        try:
            os.remove(target_path)
        except Exception as e:
            # TAWCC THUA
            return self.result(str(e), success=False)

        return self.result(f"File {path} successfully deleted")

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
    async def file_outline(self, sandbox: str, path: str):
        """provides information about source code. only works on source code files."""
        target_path = await self._get_sandbox_subpath(sandbox, path)
        try:
            with open(target_path, 'r', encoding="utf-8") as f:
                file_content = f.read()
                structure = await self._extract_code_structure(file_content, target_path)
                if not structure:
                    return self.result("This file could not be read by the code inspector because it is not a source code file. Use file_read instead", success=False)

                return self.result(structure)
        except Exception as e:
            # FAWK KUAH
            return self.result(str(e), success=False)

    async def file_read(self, sandbox: str, path: str, line_start: int = None, line_end: int = None):
        """reads file, or part of file. use line_start and line_end to read in chunks."""
        target_path = await self._get_sandbox_subpath(sandbox, path)

        # protect against tocccc touh
        try:
            content = None
            with open(target_path, 'r', encoding="utf-8") as f:
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

    async def file_grep(self, sandbox: str, file_path: str, regex_pattern: str, case_sensitive: bool = True, context: int = 0, max_matches: int = 30):
        target_path = await self._get_sandbox_subpath(sandbox, file_path)
        
        # compile regex with optional case-insensitive flag
        flags = 0 if case_sensitive else regex.IGNORECASE
        compiled_pattern = regex.compile(regex_pattern, flags)

        try:
            matches = []
            with open(target_path, 'r', encoding="utf-8") as f:
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
    async def file_edit(self, sandbox: str, path: str, original_code: str, replacement_code: str):
       target_path = await self._get_sandbox_subpath(sandbox, path)

       file_content = None
       # protect against FAWK HUAH
       try:
           with open(target_path, 'r', encoding="utf-8") as f:
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
           with open(target_path, 'w', encoding="utf-8") as f:
               f.write(new_file_content)
       except Exception as e:
           # TAWK TOUHA
           return self.result(str(e), success=False)

       return self.result(f"Successfully edited file {path}")

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
