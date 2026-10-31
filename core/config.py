import os
import ast
import copy
import core
import modules
import user_modules
import channels
import user_channels
import hashlib
import json
import inspect

config = None
_registry_cache = None
_cache_refresh_in_progress = False

SCHEMA_CACHE_FILE = ".module_cache.json"

# bump whenever the shape of cached module metadata changes (e.g. a new metadata
# field was added). a cache file written by another version is rebuilt in full on
# startup, so stale entries never serve incomplete metadata.
SCHEMA_CACHE_VERSION = 5

# the section keys the cache stores module/channel entries under
CACHE_SECTIONS = ("channels", "user_channels", "modules", "user_modules")

core_settings_schema = {
    "core": {
        "data_folder": {
            "default": "data",
            "description": "The folder where openlumara stores its data files (chats, memories, etc.)."
        },
        "auto_resume_chats": {
            "default": True,
            "description": "Whether to automatically resume the last active chat on startup."
        },
        "cmd_prefix": {
            "default": "/",
            "description": "The prefix used to determine whether something is a command. For example, when it's set to `/`, all commands must be prefixed with `/` as in `/help`. If you set it to `!`, it will be `!help` instead."
        },
        "tool_timeout": {
            "default": 30,
            "description": "Timeout in seconds for tool execution. This applies per individual tool, and is used to forcefully kill off tools that run too long."
        },
        "module_libraries": {
            "description": "A list of git repo urls containing modules, channels, skills and themes you want to be able to download and update in openlumara.",
            "default": ["https://github.com/Rose22/openlumara-rose22-content"]
        }
    },
    "api": {
        "url": {
            "default": "http://API_URL_HERE/v1",
            "description": "The base URL for the API endpoint. Get this from your chosen software (such as [llamacpp](https://llama.app/), [koboldcpp](https://koboldai.org/cpp), [lemonade](https://lemonade-server.ai/), or any other software you may prefer) or from your cloud API provider."
        },
        "key": {
            "default": "openlumara-dummy-key",
            "description": "The API key for authentication. For local, this is often unneeded unless you deliberately secured your server with an API key. When in doubt, leave it as default."
        },
        "max_context": {
            "default": 16768,
            "description": "Maximum number of tokens for the context window. This controls how much of your conversation your AI will remember. The higher the context, the further back it will remember, but how much context an AI supports depends on the model. Check your model's details page or modelcard for information on its supported context size."
        },
        "max_output_tokens": {
            "default": 8192,
            "description": "Maximum number of tokens for model output. This controls how much text your AI is allowed to generate. If you like short and sweet responses, set this to a low amount! But if you're coding or having it write entire books or something, you may want to up this value."
        },
        "max_messages": {
            "default": 200,
            "description": "Maximum number of messages to keep in conversation history. If this amount of messages is exceeded, it will trim the context window even if the token limit hasn't been reached!"
        },
        "evict_block": {
            "default": 32,
            "description": "When the message history exceeds max_messages, messages are removed in blocks of this size. (example: if set to 32, it'll remove 32 messages from history to make space for the next 32 messages)"
        },
        "use_developer_role": {
            "default": False,
            "description": "Enables the `developer` role for system prompts (see [this page](https://developers.openai.com/api/docs/guides/text#message-roles-and-instruction-following)). This helps the model distinguish between openlumara's instructions and your messages. Note: Not all models support this; unsupported models may crash if enabled.",
        },
        "custom_fields": {
            "type": "object",
            "default": {},
            "description": "Additional custom fields to send with API requests. You can put anything in here that your chosen API supports!"
        }
    },
    "model": {
        "name": {
            "default": "",
            "description": "The name of the AI model to use."
        },
        "temperature": {
            "default": 0.7,
            "description": "Sampling temperature for the model (0.0 to 2.0)."
        },
        "use_tools": {
            "default": True,
            "description": "Enable tool/function calling for the model. Turn this off if you just wanna talk to the AI and don't care for all this agentic stuff! Essentially turns it into a chatbot that can't actually do anything, but it can still answer your questions."
        },
        "dynamic_tool_loading": {
            "default": False,
            "description": "When enabled, only a small selection of tools is loaded at first, but the AI can load them dynamically from enabled openlumara modules. When disabled, all available tools are loaded at startup for immediate use.",
            "depends": "use_tools"
        },
        "preloaded_modules": {
            "default": [],
            "description": "List of module names whose tools are always preloaded at startup. Keeps frequently-used tools available immediately, everything else stays available via the dynamic tool loader.",
            "type": "list",
            "depends": "use_tools"
        },
        "automatically_compress_context": {
            "default": True,
            "description": """
When enabled, context will automatically be compressed when the threshold (defined below) is hit. This will make the AI summarize the current state of your conversation, so that it can continue where it left off without having to reprocess the entire context with every request. This will let you have an 'infinite context window' of sorts where the AI can keep working on your request forever.

When disabled, it will instead remove your old messages from context to make space for new ones - which is fine at small context sizes, but can be really slow at large context sizes. You will still have infinite context, but as soon as you hit the context window's size limit, requests will slow down massively.
            """.strip()
        },
        "context_compression_threshold": {
            "default": 0.7,
            "description": "Percentage of the context that must be full in order for the automatic compression to trigger."
        },
        "enable_thinking": {
            "default": True,
            "description": "Enable reasoning (thinking) for the model."
        },
        "keep_reasoning_in_context": {
            "default": True,
            "description": "Keep the model's reasoning process in the conversation context. If you turn this off, the model won't remember its own thoughts, just the conclusions it drew. Can be useful for saving context.",
            "depends": "enable_thinking"
        },
        "only_preserve_reasoning_for_current_agentic_loop": {
            "default": True,
            "description": "An 'agentic loop' is a chain of multiple thoughts, toolcalls, and so on, until the AI reaches a conclusion. When you make a request to the AI, such as `search the web for kitty facts and write a summary of it to a note`, it will first think, then do the web search, then think again (sometimes), then write it to a note, and then it will tell you that it's done. That's an agentic loop! So when you enable this, the AI will forget the thoughts it had in previous agentic loops, which is a huge context/token saver.",
            "depends": {"enable_thinking": True, "keep_reasoning_in_context": True},
        },
        "reasoning_effort": {
            "default": "none",
            "type": "select",
            "description": "The reasoning effort level for the model. This controls how deeply the model will think before answering, but it only works on koboldcpp and some cloud API's. Set to none to outright disable sending this with the request.",
            "options": {
                "none": 0,
                "low": 1,
                "medium": 2,
                "high": 3,
                "xhigh": 4,
                "max": 5
            },
            "depends": "enable_thinking"
        },
    },
    "channels": {
        "enabled": {
            "default": [],
            "description": "List of enabled channel names.",
            "type": "list"
        },
        "disabled": {
            "default": [],
            "description": "List of disabled channel names.",
            "type": "list"
        },
        "settings": {
            "default": {},
            "description": "Per-channel settings, keyed by channel name."
        }
    },
    "user_channels": {
        "enabled": {
            "default": [],
            "description": "List of enabled user channel names.",
            "type": "list"
        },
        "disabled": {
            "default": [],
            "description": "List of disabled user channel names.",
            "type": "list"
        },
        "settings": {
            "default": {},
            "description": "Per-user-channel settings, keyed by channel name."
        }
    },
    "modules": {
        "enabled": {
            "default": [],
            "description": "List of enabled module names.",
            "type": "list"
        },
        "disabled": {
            "default": [],
            "description": "List of disabled module names.",
            "type": "list"
        },
        "settings": {
            "default": {},
            "description": "Per-module settings, keyed by module name."
        }
    },
    "user_modules": {
        "enabled": {
            "default": [],
            "description": "List of enabled user module names.",
            "type": "list"
        },
        "disabled": {
            "default": [],
            "description": "List of disabled user module names.",
            "type": "list"
        },
        "settings": {
            "default": {},
            "description": "Per-user-module settings, keyed by module name."
        }
    }
}

DEFAULT_MODULES = (
    "tutorial",
    "docs",
    "identity",
    "models",
    "channel",
    "modules",
    "chats",
    "context",
    "memory",
    "scheduler",
    "calendar",
    "time",
    "auto_backup"
)

DEFAULT_CHANNELS = ["cli", "webui"]

def _flatten_settings(settings_dict):
    """Recursively flattens a settings dictionary by extracting 'default' values."""
    if isinstance(settings_dict, dict) and "default" in settings_dict:
        return _flatten_settings(settings_dict["default"])
    if isinstance(settings_dict, dict):
        return {k: _flatten_settings(v) for k, v in settings_dict.items()}
    return settings_dict

default_config = _flatten_settings(core_settings_schema)

class ConfigManager:
    def __init__(self, config, base_path=None):
        self.root_config = config
        self.base_path = base_path or []

    def get(self, *args, **kwargs):
        """Shorthand for accessing nested config values.
        Usage: config.get("api", "url") or config.get("api", "url", default_value)
        """
        # reload from disk
        self.root_config.load()

        default = kwargs.get("default", None)
        if not args:
            return default

        keys = list(args)
        # if the last argument is not a string (or is an empty string), treat it as an explicit default
        if keys and (not isinstance(keys[-1], str) or not keys[-1]):
            default = keys.pop()

        # start from the root config and traverse through the base path
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return default

        # Then traverse through the provided keys
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
        return current

    def set(self, key, value):
        """Set a key to a value.. duh lol"""
        current = self.root_config
        for k in self.base_path:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[key] = value
        if hasattr(self.root_config, 'save'):
            self.root_config.save()

    def to_dict(self):
        # reload from disk
        self.root_config.load()

        # Start from the root config and traverse through the base path
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return {}

        return dict(current)

    def __getitem__(self, key):
        """Access items using bracket notation: config['key']"""
        current = self.root_config
        for k in self.base_path + [key]:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                raise KeyError(key)
        return current

    def __setitem__(self, key, value):
        """Set items using bracket notation: config['key'] = value"""
        current = self.root_config
        for k in self.base_path:
            if k not in current or not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]

        current[key] = value
        if hasattr(self.root_config, 'save'):
            self.root_config.save()

    def __contains__(self, key):
        """Check if key exists: 'key' in config"""
        current = self.root_config
        for k in self.base_path:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return False
        return isinstance(current, dict) and key in current

def _discover_available_names(package):
    """
    Discover module names from filesystem WITHOUT importing them.
    This allows the config to know what modules exist without loading them.
    Folder-only layout: a folder counts only if it contains module.py or channel.py.
    """
    return core.modules.discover_module_names(package)

def _get_registry_data(enabled_channels=None, enabled_user_channels=None, enabled_modules=None, enabled_user_modules=None):
    """
    Build registry data, importing ONLY enabled modules/channels.

    Available names are discovered via filesystem scanning.
    Instances are only created for enabled items.
    """
    global _registry_cache

    # Build cache key from enabled lists
    cache_key = (
        tuple(enabled_channels or []),
        tuple(enabled_user_channels or []),
        tuple(enabled_modules or []),
        tuple(enabled_user_modules or [])
    )

    if _registry_cache is not None and _registry_cache.get('key') == cache_key:
        return _registry_cache['data']

    # Discover all available names from filesystem (no imports!)
    available_channels = _discover_available_names(channels)
    available_user_channels = _discover_available_names(user_channels)
    available_modules = _discover_available_names(modules)
    available_user_modules = _discover_available_names(user_modules)

    # Only import and instantiate ENABLED items
    chan_inst = list(core.modules.load(
        channels, core.channel.Channel, filter=enabled_channels, loading_config=True
    )) if enabled_channels else []

    user_chan_inst = list(core.modules.load(
        user_channels, core.channel.Channel, filter=enabled_user_channels, loading_config=True
    )) if enabled_user_channels else []

    mod_inst = list(core.modules.load(
        modules, core.module.Module, filter=enabled_modules, loading_config=True
    )) if enabled_modules else []

    user_mod_inst = list(core.modules.load(
        user_modules, core.module.Module, filter=enabled_user_modules, loading_config=True
    )) if enabled_user_modules else []

    result = [
        {
            "section_key": "channels",
            "instances": chan_inst,
            "available_names": available_channels,
            "names": [core.modules.get_name(m) for m in chan_inst],
            "default_names": DEFAULT_CHANNELS
        },
        {
            "section_key": "user_channels",
            "instances": user_chan_inst,
            "available_names": available_user_channels,
            "names": [core.modules.get_name(m) for m in user_chan_inst],
            "default_names": []
        },
        {
            "section_key": "modules",
            "instances": mod_inst,
            "available_names": available_modules,
            "names": [core.modules.get_name(m) for m in mod_inst],
            "default_names": DEFAULT_MODULES
        },
        {
            "section_key": "user_modules",
            "instances": user_mod_inst,
            "available_names": available_user_modules,
            "names": [core.modules.get_name(m) for m in user_mod_inst],
            "default_names": []
        }
    ]

    _registry_cache = {'key': cache_key, 'data': result}
    return result

def _get_module_schema_cache():
    """
    Returns a dictionary containing the cached schemas and checksums for all modules/channels.
    If the cache is missing or outdated, it performs a refresh.
    """
    cache_path = os.path.abspath(os.path.join(core.get_home(), SCHEMA_CACHE_FILE))
    cache = {section_key: {} for section_key in CACHE_SECTIONS}
    cache["_version"] = SCHEMA_CACHE_VERSION

    # a cache written by a different cache version holds metadata in an old
    # shape (e.g. missing 'category'). force a full rebuild in that case.
    force_full_refresh = False

    # Load existing cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                loaded = json.load(f)
            if loaded.get("_version") != SCHEMA_CACHE_VERSION:
                force_full_refresh = True
            # merge per-section so a cache file missing a section doesn't silently disable scanning for it
            for section_key in CACHE_SECTIONS:
                cache[section_key] = loaded.get(section_key, {})
        except Exception as e:
            print(f"[CORE] error while loading module cache {core.detail_error(e)}")
    else:
        print(f"[CORE] creating module cache at {cache_path}")

    # re-entrancy guard: modules may call get_schema/get_module_structure at import time (during class-body evaluation),
    # which would re-enter this function while a refresh is loading them. that causes an infinite reload loop. Break it by returning as-is.
    global _cache_refresh_in_progress
    if _cache_refresh_in_progress:
        return cache
    _cache_refresh_in_progress = True
    try:
        cache = _refresh_module_schema_cache(cache, cache_path, force_full_refresh=force_full_refresh)
    finally:
        # always release the guard, even if something unexpected blows up mid-refresh
        _cache_refresh_in_progress = False

    return cache

def _refresh_module_schema_cache(cache, cache_path, force_full_refresh=False):
    """Scan the filesystem for new/changed/deleted modules and rebuild the cache dict accordingly."""
    package_map = {
        "channels": (channels, core.channel.Channel),
        "user_channels": (user_channels, core.channel.Channel),
        "modules": (modules, core.module.Module),
        "user_modules": (user_modules, core.module.Module)
    }

    # when the on-disk cache is from another cache version, rebuild every section
    sections_to_refresh = set(package_map.keys()) if force_full_refresh else set()

    # 1. Check for deletions or changes in existing cache
    for section_key, (package, _) in package_map.items():
        available_names = _discover_available_names(package)

        if section_key not in cache.keys():
            continue

        for name in list(cache[section_key].keys()):
            if name not in available_names:
                del cache[section_key][name]
                sections_to_refresh.add(section_key)
                continue

            # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13) status:reviewed
            # detect any recursive change in the module/channel folder: files or
            # folders added, removed, renamed, or modified.
            folder_fingerprint = _get_module_folder_fingerprint(package, name)
            if not folder_fingerprint or cache[section_key][name].get("fingerprint") != folder_fingerprint:
                sections_to_refresh.add(section_key)

        # 2. Check for new modules
        if section_key not in sections_to_refresh:
            for name in available_names:
                if name not in cache[section_key]:
                    sections_to_refresh.add(section_key)
                    break

    # 3. Refresh cache if needed
    if sections_to_refresh:
        for section_key in sections_to_refresh:
            package, base_class = package_map[section_key]
            loaded_names = set()
            try:
                # Force reload modules to pick up schema changes from disk
                classes = core.modules.load(package, base_class, reload=True, loading_config=True)

                for cls in classes:
                    name = core.modules.get_name(cls)
                    loaded_names.add(name)
                    settings = getattr(cls, 'settings', {})

                    # Capture docstring and the unsafe/category class attributes
                    docstring = inspect.getdoc(cls) or ""
                    unsafe = getattr(cls, 'unsafe', False)

                    category = getattr(cls, 'category', "") or ""

                    module = inspect.getmodule(cls)
                    checksum = ""
                    if module and hasattr(module, '__file__') and module.__file__:
                        py_file = module.__file__.replace('.pyc', '')
                        checksum = _get_file_checksum(py_file) if os.path.exists(py_file) else _get_file_checksum(module.__file__)

                    cache[section_key][name] = {
                        "schema": settings,
                        "checksum": checksum,
                        "fingerprint": _get_module_folder_fingerprint(package, name),
                        "metadata": {
                            "docstring": docstring,
                            "unsafe": unsafe,  # Added to cache
                            "category": category
                        }
                    }

            except Exception as e:
                print(f"[CORE] Failed to refresh cache for {section_key}: {core.detail_error(e)}")

            try:
                for name in _discover_available_names(package):
                    if name in loaded_names:
                        continue

                    entry = cache[section_key].get(name)
                    if not isinstance(entry, dict):
                        continue

                    file_path = core.modules._get_module_file_path(package, name)
                    if not file_path:
                        continue

                    # keep the fingerprint current even for modules that could not
                    # be imported, otherwise a broken module would refresh forever.
                    entry["checksum"] = _get_file_checksum(file_path)
                    entry["fingerprint"] = _get_module_folder_fingerprint(package, name)

                    extracted = _extract_class_metadata_from_file(file_path)
                    if not extracted:
                        continue

                    metadata = entry.setdefault("metadata", {})
                    metadata["docstring"] = extracted["docstring"]
                    metadata["unsafe"] = extracted["unsafe"]
                    metadata["category"] = extracted["category"]
            except Exception as e:
                print(f"[CORE] failed to statically read metadata for {section_key}: {core.detail_error(e)}")

        try:
            with open(cache_path, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            print(f"[CORE] failed to save module cache: {core.detail_error(e)}")

    return cache

def _ast_class_attrs(node):
    """
    Read docstring/unsafe/category assignments straight off a class definition node.
    category stays None when the class does not declare one itself (so we know to
    look at its base classes).
    """
    docstring = ast.get_docstring(node) or ""
    unsafe = False
    category = None
    looks_like_module = False

    for item in node.body:
        if not isinstance(item, ast.Assign) or len(item.targets) != 1:
            continue
        target = item.targets[0]
        if not isinstance(target, ast.Name):
            continue

        if target.id in ("settings", "dependencies"):
            looks_like_module = True
        elif target.id == "unsafe" and isinstance(item.value, ast.Constant):
            unsafe = bool(item.value.value)
            looks_like_module = True
        elif target.id == "category" and isinstance(item.value, ast.Constant) and isinstance(item.value.value, str):
            category = item.value.value
            looks_like_module = True

    return {"docstring": docstring, "unsafe": unsafe, "category": category, "looks_like_module": looks_like_module}


def _dotted_name(node):
    """turns an ast Name/Attribute chain (e.g. `modules.http.Http`) into its dotted string"""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def _parse_ast(filepath):
    try:
        with open(filepath, 'r', encoding="utf-8") as f:
            return ast.parse(f.read())
    except Exception:
        return None


def _import_aliases(tree):
    """maps locally imported names to their dotted origin, e.g. `from modules.http import Http` -> Http = modules.http.Http"""
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
    return aliases


def _find_class_node(tree, class_name):
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _module_file_for_dotted(dotted_path):
    """resolves a dotted module path like `modules.http` to its entry file, without importing anything"""
    parts = dotted_path.split(".")
    if len(parts) < 2 or parts[0] not in ("modules", "user_modules", "channels", "user_channels"):
        return None

    package = {
        "modules": modules,
        "user_modules": user_modules,
        "channels": channels,
        "user_channels": user_channels,
    }[parts[0]]
    return core.modules._get_module_file_path(package, parts[1])


def _resolve_ast_category(tree, filepath, class_node, visited, depth=0):
    """
    walks a class and then its base classes to find a declared category, mirroring what
    getattr() inheritance does for importable modules. supports bases written as full
    dotted paths (modules.http.Http) as well as imported names (Http).
    """
    meta = _ast_class_attrs(class_node)
    if meta["category"] is not None:
        return meta["category"]

    if depth >= 6:
        return None

    visited.add(os.path.abspath(filepath))
    aliases = _import_aliases(tree)

    for base in class_node.bases:
        dotted = _dotted_name(base)
        if not dotted:
            continue

        # base class defined in this same file
        if "." not in dotted:
            base_node = _find_class_node(tree, dotted)
            if base_node is not None:
                result = _resolve_ast_category(tree, filepath, base_node, visited, depth + 1)
                if result is not None:
                    return result

        # base class coming from another module/channel folder
        origin = aliases.get(dotted, dotted)
        origin_parts = origin.split(".")
        base_file = _module_file_for_dotted(".".join(origin_parts[:-1]))
        if not base_file or os.path.abspath(base_file) in visited:
            continue

        base_tree = _parse_ast(base_file)
        if base_tree is None:
            continue

        base_node = _find_class_node(base_tree, origin_parts[-1])
        if base_node is None:
            continue

        result = _resolve_ast_category(base_tree, base_file, base_node, visited, depth + 1)
        if result is not None:
            return result

    return None


def _extract_class_metadata_from_file(filepath):
    """
    Statically extract docstring/unsafe/category from a module/channel file without
    importing it (same spirit as core.modules._extract_deps_from_file).

    Used as a fallback for modules that cannot be imported (e.g. their dependencies
    are not installed), so their cached metadata never goes stale. Categories are
    inherited from parent classes (across module files) just like getattr() would.
    Returns None when the file cannot be parsed or contains no class.
    """
    tree = _parse_ast(filepath)
    if tree is None:
        return None

    candidates = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        meta = _ast_class_attrs(node)
        meta["node"] = node
        candidates.append(meta)

    if not candidates:
        return None

    # prefer the class that actually looks like the module/channel class
    chosen = next((c for c in candidates if c["looks_like_module"]), candidates[0])
    category = _resolve_ast_category(tree, filepath, chosen["node"], set()) or ""

    return {"docstring": chosen["docstring"], "unsafe": chosen["unsafe"], "category": category}


def _get_module_folder_path(package, module_name):
    """returns the folder containing a module/channel entry file"""
    module_file = core.modules._get_module_file_path(package, module_name)
    if module_file:
        return os.path.dirname(module_file)

    for sub_path in getattr(package, "__path__", []):
        candidate = os.path.join(sub_path, module_name)
        if os.path.isdir(candidate):
            return candidate
    return ""


def _get_module_folder_fingerprint(package, module_name):
    """builds a recursive fingerprint for a module/channel folder.

    This intentionally uses paths, sizes and mtimes rather than file contents so
    that adding/removing/changing files is cheap to detect without hashing large
    asset folders on every startup.
    -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-13) status:reviewed
    """
    folder = _get_module_folder_path(package, module_name)
    if not folder or not os.path.isdir(folder):
        return ""

    hasher = hashlib.md5()
    skip_dirs = {
        "__pycache__",
        ".git",
        ".hg",
        ".svn",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "node_modules",
    }
    skip_exts = {".pyc", ".pyo", ".swp", ".swo", ".tmp", ".lock"}
    skip_files = {".DS_Store", "Thumbs.db"}

    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in skip_dirs)

        rel_root = os.path.relpath(root, folder).replace(os.sep, "/")
        hasher.update(f"DIR:{rel_root}\n".encode("utf-8"))

        for filename in sorted(files):
            if filename in skip_files or os.path.splitext(filename)[1] in skip_exts:
                continue

            full_path = os.path.join(root, filename)
            try:
                stat_result = os.stat(full_path)
            except OSError:
                continue

            rel_path = os.path.relpath(full_path, folder).replace(os.sep, "/")
            hasher.update(f"FILE:{rel_path}|{stat_result.st_size}|{stat_result.st_mtime_ns}\n".encode("utf-8"))

    return hasher.hexdigest()


def _get_file_checksum(filepath):
    """Calculate MD5 checksum of a file."""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""


def _merge_core_settings(user_config, schema):
    """
    Recursively merges user_config with core_settings_schema.
    This is analogous to _merge_module_settings but for core config sections.
    """
    if not isinstance(schema, dict):
        return user_config

    if isinstance(schema, dict) and "default" in schema:
        if isinstance(user_config, dict) and "default" in user_config:
            return schema["default"]
        return user_config if user_config is not None else schema["default"]

    if not isinstance(user_config, dict):
        user_config = {}

    new_config = {}
    for k, v in schema.items():
        if k in user_config:
            new_config[k] = _merge_core_settings(user_config[k], v)
        else:
            new_config[k] = _flatten_settings(v)
    return new_config

def get_schema():
    """
    Returns the config schema using the on-disk cache.
    Contains all possible module settings to allow persistence for disabled modules.
    """
    schema = _merge_core_settings({}, core_settings_schema)
    cache = _get_module_schema_cache()

    for section_key, section_cache in cache.items():
        # skip non-section bookkeeping keys (like _version)
        if section_key not in CACHE_SECTIONS:
            continue

        section = schema.setdefault(section_key, {})
        settings = section.setdefault("settings", {})
        for name, data in section_cache.items():
            # Flatten the settings here so the schema only contains values.
            # This prevents metadata (description, default) from leaking into the config file.
            settings[name] = _flatten_settings(data["schema"])

    return schema

def get_module_structure():
    """
    Returns a flat dictionary containing settings and metadata for all
    available modules, channels, and user_modules.

    Structure:
    {
        "name": {
            "settings": { ... },
            "metadata": {
                "doc": "...",
                "unsafe": True/False,
                "category": "...",
                "type": "module" | "channel" | "user_module"
            }
        }
    }
    """
    cache = _get_module_schema_cache()
    metadata_registry = {}

    # Map section keys to their descriptive type strings
    type_map = {
        "channels": "channel",
        "user_channels": "user_channel",
        "modules": "module",
        "user_modules": "user_module"
    }

    for section_key, section_cache in cache.items():
        # skip non-section bookkeeping keys (like _version)
        if section_key not in CACHE_SECTIONS:
            continue

        type_str = type_map.get(section_key, "unknown")

        for name, data in section_cache.items():
            metadata = data["metadata"]

            metadata_registry[name] = {
                "settings": data["schema"],
                "metadata": {
                    "doc": metadata["docstring"],
                    "unsafe": metadata["unsafe"],
                    # older cache entries may predate the category field
                    "category": metadata.get("category", ""),
                    "type": type_str
                }
            }

    return metadata_registry


def get_core_settings_structure():
    """
    Returns the core settings schema in a format compatible with the frontend's
    settings UI. Similar to get_module_structure() but for core config sections.

    Structure:
    {
        "section_name": {
            "settings": { ... },  # Full schema with defaults, descriptions, types
            "metadata": {
                "doc": "...",  # Description of the section
                "unsafe": False
            }
        }
    }
    """
    structure = {}
    
    for section_key, section_schema in core_settings_schema.items():
        if not isinstance(section_schema, dict):
            continue
        
        settings = {}
        description = ""
        
        for field_key, field_schema in section_schema.items():
            if not isinstance(field_schema, dict):
                continue
            
            # Extract description from the first field's schema if available
            if not description and "description" in field_schema:
                description = field_schema["description"]
            
            # Build the settings entry using the same structure as module settings
            settings[field_key] = {
                "default": field_schema.get("default"),
                "description": field_schema.get("description", ""),
                "type": field_schema.get("type"),
                "options": field_schema.get("options"),
                "unsafe": field_schema.get("unsafe", False),
                "depends": field_schema.get("depends"),
                "min": field_schema.get("min"),
                "max": field_schema.get("max"),
                "step": field_schema.get("step")
            }
        
        structure[section_key] = {
            "settings": settings,
            "metadata": {
                "doc": f"Configure {section_key.replace('_', ' ').title()}",
                "unsafe": False
            }
        }
    
    return structure

def sync_config(user_config, schema):
    """Recursively syncs structural keys from the schema."""
    if not isinstance(schema, dict) or not isinstance(user_config, dict):
        return schema

    result = dict(user_config)
    for key, schema_val in schema.items():
        if key in result:
            user_val = result[key]
            if isinstance(schema_val, (dict, list)) and len(schema_val) == 0:
                continue
            if isinstance(schema_val, dict) and isinstance(user_val, dict):
                result[key] = sync_config(user_val, schema_val)
        else:
            result[key] = schema_val
    return result

def reconcile_lists(available_names, default_names, section_config):
    """
    Updates the enabled/disabled lists based on filesystem discovery.
    available_names comes from filesystem scanning, not imports.
    """
    available = set(available_names)
    defaults = set(default_names)

    enabled = set(section_config.get("enabled", [])) & available
    disabled = set(section_config.get("disabled", [])) & available

    known = enabled | disabled
    new_items = available - known

    new_enabled = new_items & defaults
    new_disabled = new_items - defaults

    return {
        "enabled": sorted(list(enabled | new_enabled)),
        "disabled": sorted(list(disabled | new_disabled))
    }


def _merge_module_settings(current_settings, module_defaults):
    """Recursively merges current_settings with module_defaults schema."""
    if isinstance(module_defaults, dict) and "default" in module_defaults:
        if isinstance(current_settings, dict) and "default" in current_settings:
            return module_defaults["default"]
        return current_settings if current_settings is not None else module_defaults["default"]

    if not isinstance(module_defaults, dict):
        return current_settings if current_settings is not None else module_defaults

    if not isinstance(current_settings, dict):
        current_settings = {}

    new_settings = {}
    for k, v in module_defaults.items():
        if k in current_settings:
            new_settings[k] = _merge_module_settings(current_settings[k], v)
        else:
            new_settings[k] = _flatten_settings(v)
    return new_settings

def sync_module_settings(config_dict, instances, section_key, available_names):
    """
    Performs deep pruning and merging of module settings.
    - Removes settings for modules not on disk.
    - Keeps settings for disabled modules.
    - Merges defaults for enabled modules.
    """
    section = config_dict.setdefault(section_key, {})
    settings = section.setdefault("settings", {})

    # 1. Remove settings for modules that are no longer on the filesystem
    for name in list(settings.keys()):
        if name not in available_names:
            del settings[name]

    # 2. For modules that ARE on disk, handle enabled vs disabled
    for inst in instances:
        name = core.modules.get_name(inst)
        module_defaults = getattr(inst, 'settings', {})
        if not isinstance(module_defaults, dict):
            continue

        if name in settings and isinstance(settings[name], dict):
            # Module is enabled and has existing settings: merge them
            settings[name] = _merge_module_settings(settings[name], module_defaults)
            if not settings[name]:
                del settings[name]
        elif module_defaults:
            # Module is enabled but has no existing settings: provide defaults
            flat_defaults = _flatten_settings(module_defaults)
            if flat_defaults:
                settings[name] = flat_defaults

    # Note: If a module is in available_names but NOT in instances,
    # it is disabled and we leave its settings in 'settings' untouched.


def load(file_path=None):
    """
    Load config file.
    """
    if file_path:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        dirname = os.path.dirname(file_path)
    else:
        filename = "config"
        dirname = core.get_home()

    new_config = False

    global config
    global _registry_cache
    _registry_cache = None

    # file_mode 0o600, in other words chmod 600... readable only by the user, no other groups or other users
    config = core.storage.StorageDict(filename, "yaml", path=dirname, override_temporary=True, file_mode=0o600)
    if not config:
        new_config = True

    raw_config = dict(config) if config else {}

    enabled_channels = raw_config.get("channels", {}).get("enabled", [])
    if not enabled_channels and new_config:
        enabled_channels = DEFAULT_CHANNELS

    enabled_modules = raw_config.get("modules", {}).get("enabled", [])
    if not enabled_modules and new_config:
        enabled_modules = DEFAULT_MODULES

    enabled_user_modules = raw_config.get("user_modules", {}).get("enabled", [])
    enabled_user_channels = raw_config.get("user_channels", {}).get("enabled", [])

    # Use the new cached schema (contains all possible settings)
    schema = get_schema()

    # Registry only contains ENABLED instances and their available names
    registry = _get_registry_data(enabled_channels, enabled_user_channels, enabled_modules, enabled_user_modules)

    if new_config:
        target = copy.deepcopy(schema)
    else:
        target = sync_config(raw_config, schema)

    # Sync settings and reconcile lists
    for item in registry:
        # Pass available_names so we know what to prune
        sync_module_settings(target, item['instances'], item['section_key'], item['available_names'])

        state = reconcile_lists(
            item['available_names'],
            item['default_names'],
            target.get(item['section_key'], {})
        )
        target[item['section_key']]['enabled'] = state['enabled']
        target[item['section_key']]['disabled'] = state['disabled']

    config.load(target)
    config.save()

    if new_config:
        print(f"A new configuration file has been created at {config.path}.")

def get(*args, **kwargs):
    """Shorthand for accessing nested config values.
    Usage: config.get("api", "url") or config.get("api", "url", default_value)
    """
    default = kwargs.get("default", None)
    if not args:
        return default

    keys = list(args)
    # if the last argument is not a string (or is an empty string), treat it as an explicit default
    if keys and (not isinstance(keys[-1], str) or not keys[-1]):
        default = keys.pop()

    # safely resolve to a dictionary
    try:
        value = dict(config) if config else dict(default_config)
    except (TypeError, ValueError):
        value = dict(default_config)

    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value
