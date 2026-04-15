import os
import yaml
import core
import modules
import user_modules
import channels

config = None

default_config = {
    "core": {
        "data_folder": "data"
    },
    "api": {
        "url": "http://localhost:5001/v1",
        "key": "KEY_HERE",
        "max_context": 8192,
        "max_output_tokens": 8192,
        "max_messages": 200
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
                "port": 5000,
                "use_short_replies": False
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
        "settings": {}
    },
    "user_modules": {
        "enabled": [],
        "disabled": [],
        "settings": {}
    }
}

# Define defaults for auto-enabling
DEFAULT_MODULES = (
    "openlumara_prompt",
    "identity",
    "models",
    "channel",
    "chats",
    "context",
    "memory",
    "system",
    "scheduler",
    "tokens",
    "time"
)

DEFAULT_CHANNELS = ["cli", "webui"]

def sync_config(user_config, defaults):
    """
    Recursively sync config with defaults
    Inserts new keys that were added to default_config, but preserves existing values.
    """
    if not isinstance(defaults, dict):
        return defaults
    if not isinstance(user_config, dict):
        return defaults

    result = dict(user_config)

    for key, default_value in defaults.items():
        if key in result:
            user_value = result[key]

            # If the default is an empty container, skip syncing this key
            # to avoid wiping out the user's dynamic settings/lists.
            if isinstance(default_value, (dict, list)) and len(default_value) == 0:
                continue

            if isinstance(default_value, dict) and isinstance(user_value, dict):
                result[key] = sync_config(user_value, default_value)
        else:
            # Key is missing from user_config, add the default
            result[key] = default_value

    return result

def reconcile_lists(available_names, default_names, section_config):
    """
    Updates the enabled/disabled lists based on what is actually on disk
    """
    # Get current state from the loaded config
    enabled = set(section_config.get("enabled", []))
    disabled = set(section_config.get("disabled", []))
    available_names = set(available_names)

    # remove items in config that don't exist on disk anymore
    valid_enabled = enabled.intersection(available_names)
    valid_disabled = disabled.intersection(available_names)

    # find items available on disk but not in config
    known_items = valid_enabled.union(valid_disabled)
    new_items = available_names - known_items

    # add new items to the correct list
    for item in new_items:
        if item in default_names:
            valid_enabled.add(item)
        else:
            valid_disabled.add(item)

    # return updated lists
    return {
        "enabled": sorted(list(valid_enabled)),
        "disabled": sorted(list(valid_disabled))
    }

def add_module_settings(config_dict, module_instances, section_key):
    """Ensures module default settings are present without overwriting user values."""
    section_settings = config_dict.get(section_key, {}).get("settings", {})

    for mod in module_instances:
        name = core.modules.get_name(mod)
        defaults = getattr(mod, 'settings', {})
        if not defaults:
            continue

        if name not in section_settings:
            section_settings[name] = defaults.copy()
        else:
            for k, v in defaults.items():
                if k not in section_settings[name]:
                    section_settings[name][k] = v

def prune_stale_module_settings(config_dict, available_names, section_key):
    """Removes settings for modules that are no longer present on disk."""
    section = config_dict.get(section_key, {})
    if not isinstance(section, dict):
        return

    settings = section.get("settings", {})
    if not isinstance(settings, dict):
        return

    stale_keys = [k for k in settings if k not in available_names]
    for k in stale_keys:
        del settings[k]

def load(file_path = None):
    if file_path:
        filename = os.path.splitext(os.path.basename(file_path))[0]
        dirname = os.path.dirname(file_path)
    else:
        filename = "config"
        dirname = core.get_path()

    global config
    config = core.storage.StorageDict(filename, "yaml", path=dirname, autoreload=False)

    # get all "available" (enable-able) modules, user modules and channels
    available_module_instances = list(core.modules.load(modules, core.module.Module, respect_config=False))
    available_user_module_instances = list(core.modules.load(user_modules, core.module.Module, respect_config=False))
    available_channel_instances = list(core.modules.load(channels, core.channel.Channel, respect_config=False))

    # store their names for later syncing
    available_module_names = [core.modules.get_name(m) for m in available_module_instances]
    available_user_module_names = [core.modules.get_name(m) for m in available_user_module_instances]
    available_channel_names = [core.modules.get_name(c) for c in available_channel_instances]

    # load or create the config file
    if not config:
        # Create new config from scratch
        # Initialize lists based on availability and defaults
        mods_state = reconcile_lists(available_module_names, DEFAULT_MODULES, {"enabled": [], "disabled": []})
        user_mods_state = reconcile_lists(available_user_module_names, [], {"enabled": [], "disabled": []})
        chans_state = reconcile_lists(available_channel_names, DEFAULT_CHANNELS, {"enabled": [], "disabled": []})

        default_config["modules"]["enabled"] = mods_state["enabled"]
        default_config["modules"]["disabled"] = mods_state["disabled"]
        default_config["user_modules"]["enabled"] = user_mods_state["enabled"]
        default_config["user_modules"]["disabled"] = user_mods_state["disabled"]
        default_config["channels"]["enabled"] = chans_state["enabled"]
        default_config["channels"]["disabled"] = chans_state["disabled"]

        # Auto-populate the settings dictionary with defaults from the instances
        add_module_settings(default_config, available_module_instances, "modules")
        add_module_settings(default_config, available_user_module_instances, "user_modules")

        config.load(default_config)
        config.save()
        print()
        print(f"A new configuration file has been created. You can use the WebUI to easily change your settings, or manually edit it at {config.path}.")

    else:
        # load the existing config
        user_config = dict(config)

        # sync missing keys
        synced_config = sync_config(user_config, default_config)

        # add module default settings
        prune_stale_module_settings(synced_config, available_module_names, "modules")
        add_module_settings(synced_config, available_module_instances, "modules")
        prune_stale_module_settings(synced_config, available_module_names, "user_modules")
        add_module_settings(synced_config, available_user_module_instances, "user_modules")

        # sync any modules that were added upstream
        mods_state = reconcile_lists(
            available_module_names,
            DEFAULT_MODULES,
            synced_config.get("modules", {})
        )
        synced_config["modules"]["enabled"] = mods_state["enabled"]
        synced_config["modules"]["disabled"] = mods_state["disabled"]

        user_mods_state = reconcile_lists(available_user_module_names, [], synced_config.get("user_modules", {}))
        synced_config["user_modules"]["enabled"] = user_mods_state["enabled"]
        synced_config["user_modules"]["disabled"] = user_mods_state["disabled"]

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
