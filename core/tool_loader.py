import core
import inspect
import regex as re

META_TOOL_NAMES = {"tools_load"}

_TYPE_MAP = {str: "string", int: "integer", bool: "boolean", list: "array", dict: "object"}
_ARG_SECTION = "Args:"
_END_SECTIONS = ("Returns:", "Raises:", "Note:", "Example:")
_ALL_SECTIONS = (_ARG_SECTION,) + _END_SECTIONS
_PARAM_RE = re.compile(r"(\w+)(?:\s*\([^)]*\))?\s*:\s*(.+)")


class ToolLoader:
    """Manages dynamic tool loading: catalog, active set, and the tools_load meta tool."""

    def __init__(self, channel):
        self.channel = channel
        self.catalog = {}  # name -> {"tool": dict, "module": str, "method": str, "description": str}
        self.active_tools = []  # tool dicts sent to the API
        self.active_names = []  # active tool names
        self._meta_def = None  # tools_load meta tool dict (part of the baseline)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def parse_tool_docstring(self, docstring):
        """Parse a Google-style docstring into (param_descriptions, clean_description)."""
        if not docstring:
            return {}, ""

        lines = docstring.split("\n")

        # clean description: drop section headers and their indented bodies
        clean_lines = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_ALL_SECTIONS):
                skip = True
            elif skip and (not stripped or not line[:1].isspace()):
                skip = False
                if stripped:
                    clean_lines.append(line)
            elif not skip:
                clean_lines.append(line)

        # param descriptions from the Args: section
        descriptions = {}
        in_args = False
        current_param = None
        current_desc = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(_ARG_SECTION):
                in_args = True
            elif in_args and stripped in _END_SECTIONS:
                break
            elif in_args and stripped:
                match = _PARAM_RE.match(stripped)
                if match:
                    if current_param and current_desc:
                        descriptions[current_param] = " ".join(current_desc)
                    current_param = match.group(1)
                    current_desc = [match.group(2)]
                elif current_param:
                    current_desc.append(stripped)
        if current_param and current_desc:
            descriptions[current_param] = " ".join(current_desc)

        return descriptions, "\n".join(clean_lines).strip()

    def _tool_dict_from_func(self, func, tool_name):
        """Build an API tool dict from a callable."""
        param_descriptions, docstring = self.parse_tool_docstring(func.__doc__)

        properties = {}
        required = []
        for name, param in inspect.signature(func).parameters.items():
            prop = {"type": _TYPE_MAP.get(param.annotation, "string")}
            desc = param_descriptions.get(name)
            if desc:
                prop["description"] = desc
            properties[name] = prop
            if param.default == inspect.Parameter.empty:
                required.append(name)

        tool = {
            "type": "function",
            "function": {
                "name": tool_name,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }
        if docstring:
            tool["function"]["description"] = docstring
        return tool

    def _loadable_entry(self, name):
        """Return the catalog entry for a tool if loadable, else None.

        Loadable means: in the catalog, its module is enabled, and the tool
        itself is not disabled.
        """
        entry = self.catalog.get(name)
        if entry is None:
            return None
        module = self.channel.manager.modules.get(entry["module"])
        if module is None or entry["method"] in module.disabled_tools:
            return None
        return entry

    def _preloaded_modules(self):
        """Module names whose tools are preloaded at startup (model.preloaded_modules)."""
        modules = core.config.get("model", "preloaded_modules", default=[])
        return {str(m).lower() for m in modules} if isinstance(modules, list) else set()

    def _default_tools(self):
        """Cataloged tools belonging to the preloaded modules, as {name: entry}."""
        preloaded = self._preloaded_modules()
        return {
            name: entry for name, entry in self.catalog.items()
            if entry["module"] in preloaded
        }

    # ------------------------------------------------------------------
    # Catalog management
    # ------------------------------------------------------------------

    def register_module(self, module):
        """Scan a module for tool methods and add them to the catalog."""
        for func_name in type(module).__dict__:
            if func_name.startswith("_") or func_name in module.disabled_tools:
                continue
            if func_name == "result" or func_name.startswith("on_"):
                continue
            func_obj = getattr(module, func_name, None)
            if not callable(func_obj) or getattr(func_obj, "_is_command", False):
                continue

            tool_name = f"{module.name}_{func_name}"
            tool_dict = self._tool_dict_from_func(func_obj, tool_name)
            self.catalog[tool_name] = {
                "tool": tool_dict,
                "module": module.name,
                "method": func_name,
                "description": tool_dict["function"].get("description", ""),
            }

    def unregister_module(self, module):
        """Remove all catalog entries and active tools for a module."""
        prefix = f"{module.name}_"
        removed = [k for k in self.catalog if k.startswith(prefix)]
        for k in removed:
            del self.catalog[k]

        self.active_tools = [
            t for t in self.active_tools
            if not t["function"]["name"].startswith(prefix)
        ]
        self.active_names = [n for n in self.active_names if not n.startswith(prefix)]

        if removed:
            self.channel.log("core", f"unloaded {len(removed)} tools from '{module.name}'")

    # ------------------------------------------------------------------
    # Meta tool
    # ------------------------------------------------------------------

    @property
    def meta_tool_names(self):
        return META_TOOL_NAMES

    def _enabled_module_names(self):
        """Names of all currently enabled (loaded) modules. Never toggles anything."""
        return sorted(self.channel.manager.modules.keys())

    def _build_meta_def(self):
        """Build the tools_load meta tool dict with its dynamic description."""
        modules = ", ".join(self._enabled_module_names()) or "(none currently enabled)"
        return {
            "type": "function",
            "function": {
                "name": "tools_load",
                "description": (
                    "Loads all tools belonging to a module into your active toolset. "
                    "The module must already be enabled; this only loads its tools, "
                    "it does not enable or disable modules. "
                    f"Currently enabled modules (pass one of these as module_name): {modules}."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {"module_name": {"type": "string"}},
                    "required": ["module_name"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        }

    def register_meta_tools(self):
        """Register the tools_load meta tool as the baseline active set (idempotent)."""
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return
        if self._meta_def:
            return

        self._meta_def = self._build_meta_def()
        self.active_tools = [self._meta_def]
        self.active_names = ["tools_load"]

    def refresh_meta_tool_descriptions(self):
        """Rebuild the dynamic tools_load description with the current module list."""
        if not self._meta_def:
            return
        self._meta_def = self._build_meta_def()
        for i, tool in enumerate(self.active_tools):
            if tool["function"]["name"] == "tools_load":
                self.active_tools[i] = self._meta_def
                break

    def get_meta_callable(self, tool_name):
        """Return the bound method for a meta tool name."""
        if tool_name == "tools_load":
            return self.tools_load
        return None

    # ------------------------------------------------------------------
    # Active set management
    # ------------------------------------------------------------------

    def _baseline_tools(self):
        """(tools, names) for the baseline: the meta tool + loadable default-module tools."""
        tools, names = [], []
        if self._meta_def:
            tools.append(self._meta_def)
            names.append("tools_load")
        for name, entry in self._default_tools().items():
            if name in names or self._loadable_entry(name) is None:
                continue
            tools.append(entry["tool"])
            names.append(name)
        return tools, names

    def load_default_tools(self):
        """Preload all tools of the preloaded modules (idempotent; skips active ones)."""
        if not core.config.get("model", "dynamic_tool_loading", default=True):
            return
        if not self._meta_def:
            return

        loaded = []
        for name, entry in self._default_tools().items():
            if name in self.active_names or self._loadable_entry(name) is None:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)
            loaded.append(name)

    def reset_for_new_chat(self):
        """Reset active tools to the baseline (meta tool + default tools)."""
        if core.config.get("model", "dynamic_tool_loading", default=True):
            self.active_tools, self.active_names = self._baseline_tools()
        else:
            self.active_tools = []
            self.active_names = []
            self.load_all_tools()

    def load_all_tools(self):
        """Load every loadable tool from the catalog into the active set."""
        for name in self.catalog:
            entry = self._loadable_entry(name)
            if entry is None or name in self.active_names:
                continue
            self.active_tools.append(entry["tool"])
            self.active_names.append(name)

    # ------------------------------------------------------------------
    # Per-chat tool persistence
    # ------------------------------------------------------------------

    def get_active_non_baseline_modules(self):
        """Modules whose tools are active but that are NOT part of the baseline.

        This is the set of modules the AI explicitly loaded for this chat; it
        gets persisted per-chat so it can be restored on load.
        """
        baseline_modules = self._preloaded_modules()
        modules = set()
        for name in self.active_names:
            entry = self.catalog.get(name)
            if entry is None or entry["module"] in baseline_modules:
                continue
            modules.add(entry["module"])
        return sorted(modules)

    def persist_active_tools(self):
        """Persist active non-baseline modules to the chat's metadata (no-op if no chat)."""
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        chat.set_loaded_modules(self.get_active_non_baseline_modules())

    def restore_chat_tools(self):
        """Load the modules persisted in the chat's metadata (call after reset_for_new_chat)."""
        chat = self.channel.context.chat
        if chat is None or chat.current is None:
            return
        for module_name in chat.get_loaded_modules():
            self._load_module_tools(module_name)

    # ------------------------------------------------------------------
    # Meta tool implementation
    # ------------------------------------------------------------------

    def _load_module_tools(self, module_name):
        """Load all cataloged tools of an enabled module. Never enables/disables modules.

        Handles module availability, disabled checks, and dedup. Does NOT
        persist to chat metadata.
        """
        module_name = str(module_name).lower().strip()
        module = self.channel.manager.modules.get(module_name)
        if module is None:
            return {
                "status": "error",
                "unknown_module": module_name,
                "enabled_modules": self._enabled_module_names(),
            }

        loaded = []
        already_loaded = []
        disabled = []
        for name, entry in self.catalog.items():
            if entry["module"] != module_name:
                continue
            if entry["method"] in module.disabled_tools:
                disabled.append(name)
            elif name in self.active_names:
                already_loaded.append(name)
            else:
                self.active_tools.append(entry["tool"])
                self.active_names.append(name)
                loaded.append(name)

        result = {"loaded": loaded, "already_loaded": already_loaded}
        if disabled:
            result["disabled"] = disabled
        return result

    async def tools_load(self, module_name: str):
        """Loads all tools of an enabled module into your active toolset. This only loads tools; it does not enable or disable modules. Pass the module name shown in this tool's description."""
        result = self._load_module_tools(module_name)

        if result.get("status") == "error":
            return {
                "status": "error",
                "content": (
                    f"No enabled module named '{result['unknown_module']}'. "
                    f"Enabled modules: {', '.join(result['enabled_modules'])}."
                ),
            }

        # persist the current tool state to the active chat's metadata so it
        # can be restored when this chat is loaded again
        self.persist_active_tools()

        has_success = bool(result["loaded"] or result["already_loaded"])
        return {"status": "success" if has_success else "error"}
