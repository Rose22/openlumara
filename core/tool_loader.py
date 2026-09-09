import core
import inspect
import regex as re

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
                if any(stripped.startswith(h) for h in {"Returns:", "Raises:", "Note:", "Example:"}):
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

    def reset_for_new_chat(self):
        """Reset active tools to the meta-tool baseline."""
        self.active_tools = list(self._meta_tool_defs)
        self.active_names = list(self.meta_tool_names)

    # ------------------------------------------------------------------
    # Meta tool implementations
    # ------------------------------------------------------------------

    async def tools_lookup(self, query: str, limit: int = 10):
        """Search your currently available toolset by name or description. This tool ONLY lists tools that are already loaded in your current environment. It is NOT a web search, file search, or general knowledge search. Use this to discover what actions/capabilities you have access to, not to search the internet or filesystem."""
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

    async def tools_load(self, names):
        """Load tools by exact name (from tools_lookup results)"""
        if isinstance(names, str):
            names = [names]

        max_active = core.config.get("core", "max_active_tools", default=50)
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

        # Respect the cap
        if len(self.active_names) + len(new_to_add) > max_active:
            new_to_add = new_to_add[:max_active - len(self.active_names)]

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

        has_success = bool(loaded or already_loaded)
        return {
            "status": "success" if has_success else "error",
            "content": result,
        }
