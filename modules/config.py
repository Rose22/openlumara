import core
import json

class Config(core.module.Module):
    """Lets the AI manage the OpenLumara configuration/settings for you"""

    _header = "OpenLumara config"

    async def on_system_prompt(self):
        try:
            return json.dumps(core.config.config, indent=2)
        except:
            return None

    def _convert_type(self, value: str):
        """
        Converts string inputs from the CLI/Chat into appropriate Python types.
        """
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # Try integer conversion
        try:
            # We use a check to see if it's a valid integer representation
            if value.lstrip('-').isdigit():
                return int(value)
        except ValueError:
            pass

        # Try float conversion
        try:
            return float(value)
        except ValueError:
            pass

        # Default to string
        return value

    async def set(self, path: list, value: str):
        """
        Sets a configuration value at a nested path.

        Args:
            path: A list of keys representing the nested path (e.g., ["api", "url"]).
            value: The value to set (as a string, will be type-converted).
        """
        if not path:
            return self.result("Path cannot be empty", False)

        typed_value = self._convert_type(value)

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
