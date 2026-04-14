import os
import yaml
import core
import modules
import channels

import globals

pathToUse = globals.configPath if globals.configPath is not None else None
nameToUse = os.path.splitext(os.path.basename(pathToUse))[0] if pathToUse is not None else "config"
dataDir = os.path.dirname(pathToUse) if pathToUse is not None else "."
config = core.storage.StorageDict(nameToUse, "yaml", data_dir=dataDir, autoreload=False)

default_config = {
    "core": {
        "data_folder": "data"
    },
    "api": {
        "url": "http://localhost:5001/v1",
        "key": "KEY_HERE",
        "max_context": 8192,
        "max_output_tokens": 8192,
        "max_messages": 200,
        "insecure_skip_tls_verify": False
    },
    "model": {
        "name": "MODEL_HERE",
        "temperature": 0.2,
        "use_tools": True
    },
    "channels": {
        "enabled": ["cli", "webui"],
        "disabled": [],
        "settings": {
            "webui": {
                "host": "localhost",
                "port": 5000
            },
            "discord": {
                "token": "TOKEN_HERE"
            },
            "telegram": {
                "token": "TOKEN_HERE"
            },
            "matrix": {
                "homeserver": "https://matrix.org",
                "user_id": "@your_bot:matrix.org",
                "password": "your_password_here",
                "device_name": "OpenLumara"
            }
        }
    },
    "modules": {
        "enabled": [],
        "disabled": [],
        "disabled_prompts": [],
        "settings": {
            "files": {
                "sandbox_folder": "~/sandbox"
            }
        }
    }
}

# Define defaults for auto-enabling
DEFAULT_MODULES = (
    "agent_framework_awareness",
    "identity",
    "models",
    "channel",
    "chats",
    "context",
    "memory",
    "notes",
    "system",
    "scheduler",
    "tokens",
    "time"
)

DEFAULT_CHANNELS = ["webui"] # "cli" is disabled for Esobold

def sync_config(user_config, defaults):
    """
    Recursively sync user config with defaults.
    Ensures new keys are added, but preserves user values.
    """
    if not isinstance(defaults, dict):
        return defaults

    result = {}

    for key, default_value in defaults.items():
        if key in user_config:
            user_value = user_config[key]
            if isinstance(default_value, dict) and isinstance(user_value, dict):
                result[key] = sync_config(user_value, default_value)
            else:
                # Keep user's value for existing keys
                result[key] = user_value
        else:
            # Add missing key with default value
            result[key] = default_value

    return result

def reconcile_lists(available_names, default_names, section_config):
    """
    Updates the enabled/disabled lists based on what is actually on disk.
    - Removes items that no longer exist.
    - Adds new items (enabling them if in default_names, else disabling).
    """
    # Get current state from the loaded config
    enabled = set(section_config.get("enabled", []))
    disabled = set(section_config.get("disabled", []))

    # 1. Remove "ghosts": Items in config that don't exist on disk anymore
    valid_enabled = enabled.intersection(available_names)
    valid_disabled = disabled.intersection(available_names)

    # 2. Find new items: Available on disk but not in config
    known_items = valid_enabled.union(valid_disabled)
    new_items = available_names - known_items

    # 3. Add new items to the correct list
    for item in new_items:
        if item in default_names:
            valid_enabled.add(item)
        else:
            valid_disabled.add(item)

    # Return updated lists (sorted for clean config files)
    return {
        "enabled": sorted(list(valid_enabled)),
        "disabled": sorted(list(valid_disabled))
    }

# --- Main Setup Logic ---

# get all available modules
available_module_names = set()
for module in modules.get_all(respect_config=False):
    available_module_names.add(core.module.get_name(module))

# get all available channels
available_channel_names = set()
for channel in channels.get_all(respect_config=False):
    channel_name = core.module.get_name(channel)
    available_channel_names.add(channel_name)

# load or create the config file
if not config:
    # Create new config from scratch
    # Initialize lists based on availability and defaults
    mods_state = reconcile_lists(available_module_names, DEFAULT_MODULES, {"enabled": [], "disabled": []})
    chans_state = reconcile_lists(available_channel_names, DEFAULT_CHANNELS, {"enabled": [], "disabled": []})

    default_config["modules"]["enabled"] = mods_state["enabled"]
    default_config["modules"]["disabled"] = mods_state["disabled"]
    default_config["channels"]["enabled"] = chans_state["enabled"]
    default_config["channels"]["disabled"] = chans_state["disabled"]

    config.load(default_config)
    config.save()
    print()
    print(f"A new configuration file has been created. You can use the WebUI to easily change your settings, or manually edit it at {config.path}.")

else:
    # load the existing config
    user_config = dict(config)

    # sync missing keys
    synced_config = sync_config(user_config, default_config)

    # sync any modules that were added upstream
    mods_state = reconcile_lists(
        available_module_names,
        DEFAULT_MODULES,
        synced_config.get("modules", {})
    )
    synced_config["modules"]["enabled"] = mods_state["enabled"]
    synced_config["modules"]["disabled"] = mods_state["disabled"]

    # ditto for channels
    chans_state = reconcile_lists(
        available_channel_names,
        DEFAULT_CHANNELS,
        synced_config.get("channels", {})
    )
    synced_config["channels"]["enabled"] = chans_state["enabled"]
    synced_config["channels"]["disabled"] = chans_state["disabled"]

    # save if changes occurred
    if synced_config != user_config:
        config.clear()
        config.update(synced_config)
        config.save()
        core.log("core", "Your configuration was updated with new stuff!")

def get(*args, **kwargs):
    """shorthand for accessing config values"""
    return config.get(*args, **kwargs)
