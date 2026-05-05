import core
import json
import copy

class Config(core.module.Module):
    """Lets the AI manage the OpenLumara configuration/settings for you"""

    unsafe = True
    _header = "OpenLumara config"

    settings = {
        "put_config_in_system_prompt": True
    }

    def _redact_sensitive_info(self, data):
        """Recursively redacts sensitive information from a dictionary or list."""
        sensitive_keywords = ["token", "key", "secret", "password", "auth", "credential"]

        if isinstance(data, dict):
            new_dict = {}
            for k, v in data.items():
                # Check if the key contains any of the sensitive keywords
                if any(kw in k.lower() for kw in sensitive_keywords):
                    new_dict[k] = "****"
                elif isinstance(v, (dict, list)):
                    new_dict[k] = self._redact_sensitive_info(v)
                else:
                    new_dict[k] = v
            return new_dict
        elif isinstance(data, list):
            return [self._redact_sensitive_info(item) for item in data]
        else:
            return data

    async def on_system_prompt(self):
        if not self.config.get("put_config_in_system_prompt"):
            return None

        try:
            # Deep copy to avoid mutating the actual live configuration
            config_data = copy.deepcopy(core.config.config)
            redacted_config = self._redact_sensitive_info(config_data)
            return json.dumps(redacted_config)
        except Exception as e:
            core.log_error("error while inserting config into system prompt", e)
            return None

    async def set(self, path: list, value: str):
        if not path:
            return self.result("Path cannot be empty", False)

        typed_value = core.commands._convert_type(value)

        try:
            # Access the StorageDict instance from the config module
            target = core.config.config
            if target is None:
                return self.result("Configuration is not loaded. Please restart or wait for system initialization.", False)

            # Traverse the dictionary following the path
            current = target
            for i, key in enumerate(path[:-1]):
                # If the key doesn't exist or the current level isn't a dictionary,
                # create a new dictionary to allow for deep nesting.
                if key not in current or not isinstance(current[key], dict):
                    current[key] = {}
                current = current[key]

            # Set the final value
            current[path[-1]] = typed_value

            # Persist changes to the YAML file
            core.config.config.save()

            return self.result(f"Config updated: {' -> '.join(path)} = {typed_value}")
        except Exception as e:
            return self.result(f"Failed to update config: {e}", False)
