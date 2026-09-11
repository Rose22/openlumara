import core
import inspect
import regex as re

# Tools that are ALWAYS preloaded at startup, on top of the two meta tools
# (tools_lookup / tools_load), even when dynamic tool loading is enabled.
#
# This keeps a small handful of frequently-used tools available immediately
# without bloating the context with the entire catalog. Everything else stays
# available on demand via tools_lookup -> tools_load.
#
# Edit this list to change which tools are preloaded by default. Names use the
# standard "<module>_<method>" format (e.g. "memory_create").
DEFAULT_TOOLS = [
    "memory_create",
    "memory_search",
    "memory_edit",
    "memory_delete",
    "memory_pin",
    "memory_unpin",
    "web_search"
]

class ToolLoader:
    """Manages dynamic tool loading: catalog, active set, and meta tools."""

    def __init__(self, channel):
        self.channel = channel
        self.catalog = {}  # name -> {"tool": dict, "module": str, "method": str, "description": str}
        self.active_tools = []  # tool dicts sent to the API
        self.active_names = []  # active tool names
        self._meta_tool_defs = []  # the two meta tool dicts (baseline active set)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def parse_tool_docstring(self, docstring):
        """
        Parses Google-style docstring to extract param descriptions
        and returns a cleaned docstring without the Args/Returns sections.
        """
        if not docstring:
            return {}, ""

        descriptions = {}
        lines = docstring.split("\n")
        clean_lines = []

        skip_section = False
        section_headers = {"Args:", "Returns:", "Raises:", "Note:", "Example:"}

        for line in lines:
            stripped = line.strip()

            # Check if we're entering a section to skip
            if any(stripped.startswith(header) for header in section_headers):
                skip_section = True
                continue

            # Check if we're still in a skip section (indented line)
            if skip_section:
                # Empty line or unindented line means end of section
                if stripped == "" or (line and not line[0].isspace() and stripped):
                    # But if it's another section header, stay in skip mode
                    if not any(stripped.startswith(h) for h in section_headers):
                        skip_section = False
                        if stripped:
                            clean_lines.append(line)
                continue

            clean_lines.append(line)

        # Now parse Args section separately for descriptions
        in_args = False
        current_param = None
        current_desc = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith("Args:"):
                in_args = True
                continue

            if in_args:
                # Only treat as section end if the line is EXACTLY the header (no content after colon)
                if stripped in {"Returns:", "Raises:", "Note:", "Example:"}:
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)
                    break

                if not stripped:
                    continue

                # Match: "param_name: description" or "param_name (type): description"
                match = re.match(r"(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)", stripped)
                if match:
                    # Save previous param if exists
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)

                    current_param = match.group(1)
                    current_desc = [match.group(2)]
                elif current_param and stripped:
                    # Continuation of previous param description
                    current_desc.append(stripped)

        # Save last param
        if current_param and current_desc:
            descriptions[current_param] = " ".join(current_desc)

        # Clean up the description (remove leading/trailing whitespace, empty lines)
        clean_doc = "\n".join(clean_lines).strip()

        return descriptions, clean_doc

    def _tool_dict_from_func(self, func, tool_name):
        """Build a tool dict from a callable using existing Manager rules."""
        param_descriptions, docstring = self.parse_tool_docstring(
            func.__doc__
        )

        func_params = dict(inspect.signature(func).parameters)

        func_params_translated = {}
        required_args = []
        for param_name, param in func_params.items():
            param_annotation = param.annotation
            if param_annotation == inspect.Parameter.empty:
                param_type = "string"
            elif param_annotation == str:
                param_type = "string"
            elif param_annotation == int:
                param_type = "integer"
            elif param_annotation == bool:
                param_type = "boolean"
            elif param_annotation == list:
                param_type = "array"
            elif param_annotation == dict:
                param_type = "object"
            else:
                param_type = "string"

            if param.default == inspect.Parameter.empty:
                required_args.append(param_name)

            func_param_desc = param_descriptions.get(param_name)
            func_params_translated[param_name] = {"type": param_type}
            if func_param_desc:
                func_params_translated[param_name]["description"] = func_param_desc

        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "parameters": {
                    "type": "object",
                    "properties": func_params_translated,
                    "required": required_args,
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }

        if docstring:
            tool["function"]["description"] = docstring

        return tool

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    def register_module(self, module):
        """Scan module for tool methods and add them to the catalog."""
        for func_name in type(module).__dict__:
            if func_name.startswith("_"):
                continue
            if func_name == "result" or func_name.startswith("on_"):
                continue
            if func_name in module.disabled_tools:
                continue

            try:
                func_obj = getattr(module, func_name)
            except Exception:
                continue

            if not callable(func_obj):
                continue

            if getattr(func_obj, "_is_command", False):
                continue

            tool_name = f"{module.name}_{func_name}"
            tool_dict = self._tool_dict_from_func(func_obj, tool_name)
            desc = tool_dict["function"].get("description", "")
            self.catalog[tool_name] = {
                "tool": tool_dict,
                "module": module.name,
                "method": func_name,
                "description": desc,
            }

    def unregister_module(self, module):
        """Remove all catalog entries and active tools for a module."""
        prefix = f"{module.name}_"
        # Remove from catalog
        keys_to_remove = [k for k in self.catalog if k.startswith(prefix)]
        for k in keys_to_remove:
            del self.catalog[k]

        # Remove from active set
        self.active_tools = [
            t for t in self.active_tools
            if not t["function"]["name"].startswith(prefix)
        ]
        self.active_names = [
            n for n in self.active_names
            if not n.startswith(prefix)
        ]
        if keys_to_remove:
            self.channel.log(
                "core",
                f"unloaded {len(keys_to_remove)} tools from '{module.name}'"
            )

    # ------------------------------------------------------------------
    # Meta tools
    # ------------------------------------------------------------------

    @property
    def meta_tool_names(self):
        return {"tools_lookup", "tools_load"}

    def register_meta_tools(self):
        """Build and register the two meta tools; set as baseline active set."""
        # When dynamic tool loading is off, don't load meta tools
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return

        if self._meta_tool_defs:
            # Already registered (idempotent)
            return

        def tools_lookup(query: str, limit: int = 10):
            """Search your currently available tools by name or description. Only lists tools already loaded in your environment. NOT a web search or file search."""
            pass

        def tools_load(names: list):
            """Load tools by exact name. Use tools_lookup first to find available tools."""
            pass

        search_dict = self._tool_dict_from_func(tools_lookup, "tools_lookup")
        load_dict = self._tool_dict_from_func(tools_load, "tools_load")

        self._meta_tool_defs = [search_dict, load_dict]
        self.active_tools = list(self._meta_tool_defs)
        self.active_names = ["tools_lookup", "tools_load"]

        self.channel.log("core", "Registered meta tools: tools_lookup, tools_load")

    def get_meta_callable(self, tool_name):
        """Return the bound method for a meta tool name."""
        if tool_name == "tools_lookup":
            return self.tools_lookup
        elif tool_name == "tools_load":
            return self.tools_load
        return None

    def _resolve_default_entry(self, name):
        """Return the catalog entry for a default tool if it is currently loadable.

        A tool is loadable if it is in the catalog, its module is enabled/loaded,
        and the tool itself is not disabled.
        """
        entry = self.catalog.get(name)
        if entry is None:
            return None
        module = self.channel.manager.modules.get(entry["module"])
        if module is None:
            return None
        if entry["method"] in module.disabled_tools:
            return None
        return entry

    def _baseline_tools(self):
        """Return (tools, names) for the baseline active set.

        The baseline is the two meta tools plus any hardcoded default tools that
        are currently loadable.
        """
        tools = list(self._meta_tool_defs)
        names = ["tools_lookup", "tools_load"]
        for name in DEFAULT_TOOLS:
            if name in names:
                continue
            entry = self._resolve_default_entry(name)
            if entry is None:
                continue
            tools.append(entry["tool"])
            names.append(name)
        return tools, names

    def load_default_tools(self):
        """Preload the hardcoded default tools into the current active set.

        Safe to call multiple times (at startup and after module reloads). Only
        adds tools that are currently loadable and not already active. Default
        tools are part of the baseline.
        """
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return
        if not self._meta_tool_defs:
            return

        loaded = []
        for name in DEFAULT_TOOLS:
            if name in self.active_names:
                continue
            entry = self._resolve_default_entry(name)
            if entry is None:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)
            loaded.append(name)

        if loaded:
            self.channel.log("core", f"Preloaded default tools: {', '.join(loaded)}")

    def reset_for_new_chat(self):
        """Reset active tools to the baseline (meta tools + default tools)."""
        if core.config.get("model", "dynamic_tool_loading", default=True):
            self.active_tools, self.active_names = self._baseline_tools()
        else:
            self.active_tools = []
            self.active_names = []
            self.load_all_tools()

    # ------------------------------------------------------------------
    # Per-chat tool persistence
    # ------------------------------------------------------------------

    def get_active_non_baseline_names(self):
        """Return the active tool names that are NOT part of the baseline.

        The baseline is the two meta tools plus the hardcoded default tools.
        Everything else is a tool the AI explicitly loaded for this chat, and
        is the set we persist per-chat so it can be restored on load.
        """
        baseline_set = set(self.meta_tool_names) | set(DEFAULT_TOOLS)
        return [n for n in self.active_names if n not in baseline_set]

    def persist_active_tools(self):
        """Persist the current non-baseline active tools to the active chat's metadata.

        Safe to call any time; it does nothing if there is no active chat.
        """
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        chat.set_loaded_tools(self.get_active_non_baseline_names())

    def restore_chat_tools(self):
        """Load the tools persisted in the active chat's metadata into the active set.

        Should be called right after reset_for_new_chat() when loading/switching
        to a chat, so that the chat picks up the tools it had before.
        """
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        names = chat.get_loaded_tools()
        if not names:
            return
        self._load_tool_names(names)

    # ------------------------------------------------------------------
    # Meta tool implementations
    # ------------------------------------------------------------------

    async def tools_lookup(self, query: str, limit: int = 10):
        """Search your currently available toolset by name or description. This tool ONLY lists tools that are already available for loading into your current environment. It is NOT a web search, file search, or general knowledge search. Use this to discover what actions/capabilities you have access to, not to search the internet or filesystem."""
        if not query:
            return {
                "status": "success",
                "content": "No tools matched. Try different or fewer keywords.",
            }

        query_lower = query.lower()
        query_tokens = [t for t in query_lower.split() if len(t) >= 3]

        scored = []
        for name, entry in self.catalog.items():
            desc = entry["description"].lower()
            module = entry["module"].lower()
            score = 0

            if name == query_lower:
                score += 100
            elif name.startswith(query_lower):
                score += 80
            elif query_lower in name:
                score += 60
            else:
                for token in query_tokens:
                    if token in name:
                        score += 3
                    if token in desc:
                        score += 1

            if score > 0:
                truncated_desc = entry["description"][:160]
                scored.append({
                    "name": name,
                    "description": truncated_desc,
                    "loaded": name in self.active_names,
                    "score": score,
                })

        scored.sort(key=lambda x: -x["score"])
        top = scored[:limit]

        if not top:
            return {
                "status": "success",
                "content": "No tools matched. Try different or fewer keywords.",
            }

        # Remove the internal score field before returning
        for item in top:
            del item["score"]

        return {"status": "success", "content": top}

    def _load_tool_names(self, names):
        """Core logic to load tools by exact name. Returns a result dict.

        Handles catalog lookup, module availability, disabled checks, and
        dedup. Does NOT persist to chat metadata.
        """
        if isinstance(names, str):
            names = [names]

        unknown = []
        disabled = []
        already_loaded = []
        loaded = []

        new_to_add = []
        for name in names:
            if name in self.catalog:
                entry = self.catalog[name]
                module = self.channel.manager.modules.get(entry["module"])
                if module is None:
                    unknown.append(name)
                    continue
                if entry["method"] in module.disabled_tools:
                    disabled.append(
                        f"{name} is disabled by the {entry['module']} module"
                    )
                    continue
                if name in self.active_names:
                    already_loaded.append(name)
                    continue
                new_to_add.append(name)
            else:
                unknown.append(name)

        for name in new_to_add:
            entry = self.catalog[name]
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)
            loaded.append(name)

        result = {}
        if loaded:
            result["loaded"] = loaded
        if already_loaded:
            result["already_loaded"] = already_loaded
        if unknown:
            result["unknown"] = unknown
        if disabled:
            result["disabled"] = disabled

        if not result:
            result = {"loaded": []}

        return result

    async def tools_load(self, names):
        """Load tools by exact name (from tools_lookup results)"""
        result = self._load_tool_names(names)
        has_success = bool(result.get("loaded") or result.get("already_loaded"))

        # persist the current tool state to the active chat's metadata so it
        # can be restored when this chat is loaded again
        self.persist_active_tools()

        return {
            "status": "success" if has_success else "error"
        }

    def load_all_tools(self):
        """Load all tools from the catalog into the active set."""
        for name, entry in self.catalog.items():
            module = self.channel.manager.modules.get(entry["module"])
            if module is None:
                continue
            if entry["method"] in module.disabled_tools:
                continue
            if name in self.active_names:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)
