import os
import yaml
import core
import modules
import channels

# Config will be initialized after all core imports are ready
config = None

def _create_config():
    """Create config StorageDict, respecting path override if set."""
    config_path_override = core.get_config_path()
    if config_path_override:
        # User provided full path to config file
        config_dir = os.path.dirname(config_path_override)
        config_name = os.path.splitext(os.path.basename(config_path_override))[0]
        if not config_dir:
            config_dir = "."
        core.log("config", f"Using custom config path: {config_path_override}")
        return core.storage.StorageDict(config_name, "yaml", data_dir=config_dir, autoreload=True)
    else:
        # Use default location: config/config.yml
        default_location = core.get_path("config/config")
        core.log("config", f"Using default config path: {default_location}.yml")
        return core.storage.StorageDict("config", "yaml", data_dir="config", autoreload=True)

def initialize_config():
    """Initialize config after all core imports are ready."""
    global config
    config = _create_config()
    
    # Build default config with channel/module lists
    default_config_data = dict(default_config)
    
    for channel in channels.get_all(respect_config=False):
        channel_name = core.module.get_name(channel)
        if channel == "debug":
            continue

        if channel_name not in default_config_data.get("channels").get("enabled"):
            default_config_data["channels"]["disabled"].append(channel_name)

    for module in modules.get_all(respect_config=False):
        module_name = core.module.get_name(module)
        if module_name in default_modules:
            default_config_data["modules"]["enabled"].append(module_name)
        else:
            default_config_data["modules"]["disabled"].append(module_name)
    
    # Sync config file with defaults
    if not config:
        config.load(default_config_data)
        config.save()
        print()
        print(f"A new configuration file has been created. You can use the WebUI to easily change your settings, or manually edit it at {config.path}.")
    else:
        user_config = dict(config)
        synced_config = sync_config(user_config, default_config_data)
        if synced_config != user_config:
            config.clear()
            config.update(synced_config)
            config.save()
            core.log("core", "Your configuration file was updated with new settings")

def reload_config():
    """Reinitialize config with current path override (useful after set_config_path)."""
    global config
    initialize_config()


default_config = {
    "data_dir": "data",
    "api": {
        "url": "http://localhost:5001/v1",
        "key": "KEY_HERE",
        "insecure_skip_tls_verify": False,
        "max_context": 8192,
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
                "device_id": "opticlaw-bot",
                "device_name": "Opticlaw"
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

default_modules = (
    "modules",
    "models",
    "channel",
    "identity",
    "chats",
    "context",
    "memory",
    "notes",
    "system",
    "scheduler",
    "tokens",
    "time"
)

def sync_config(user_config, defaults):
    """
    recursively sync user config with defaults
    """
    # Base case: if defaults isn't a dict, can't recurse further
    if not isinstance(defaults, dict):
        return defaults

    result = {}

    for key, default_value in defaults.items():
        if key in user_config:
            user_value = user_config[key]
            # Recurse if both are dicts
            if isinstance(default_value, dict) and isinstance(user_value, dict):
                result[key] = sync_config(user_value, default_value)
            else:
                # Key exists - keep the user's value
                result[key] = user_value
        else:
            # Key missing from user config - add default
            result[key] = default_value

    return result

def get(*args, **kwargs):
    """shorthand for accessing config values"""

    return config.get(*args, **kwargs)
