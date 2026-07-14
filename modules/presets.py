"""Config presets module for OpenLumara.

Allows users to save and load configuration presets for quick switching
between different agent configurations (e.g., Coder, Researcher, Writer).

Usage:
    /preset save coder     - Save current config as "coder" preset
    /preset load coder     - Load "coder" preset
    /preset list           - List all saved presets
    /preset delete coder   - Delete "coder" preset
"""

import core
import json
import os
import copy
from pathlib import Path


PRESETS_DIR = Path.home() / ".openlumara" / "presets"


class Presets(core.module.Module):
    """Manage configuration presets for quick switching between agent modes."""

    header = "Config presets"

    settings = {
        "auto_create_presets_dir": {
            "description": "Automatically create presets directory if it doesn't exist",
            "default": True
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)

    def _get_preset_path(self, name: str) -> Path:
        """Get the file path for a preset."""
        safe_name = "".join(c for c in name if c.isalnum() or c in "-_")
        return PRESETS_DIR / f"{safe_name}.yaml"

    async def save(self, name: str, description: str = "") -> str:
        """Save current configuration as a preset."""
        if not name:
            return self.result("Please provide a preset name.", success=False)

        preset_path = self._get_preset_path(name)
        
        # Get current config (redact sensitive info)
        current_config = copy.deepcopy(core.config.config)
        redacted = self._redact_sensitive(current_config)
        
        preset_data = {
            "name": name,
            "description": description,
            "config": redacted
        }
        
        import yaml
        with preset_path.open("w") as f:
            yaml.dump(preset_data, f, default_flow_style=False)
        
        return self.result(f"✅ Preset '{name}' saved to {preset_path}")

    async def load(self, name: str) -> str:
        """Load a configuration preset."""
        if not name:
            return self.result("Please provide a preset name.", success=False)

        preset_path = self._get_preset_path(name)
        if not preset_path.exists():
            available = self._list_presets()
            return self.result(
                f"Preset '{name}' not found. Available: {', '.join(available) or 'none'}",
                success=False
            )

        import yaml
        with preset_path.open() as f:
            preset_data = yaml.safe_load(f)

        # Apply preset (non-destructive merge)
        preset_config = preset_data.get("config", {})
        self._apply_preset(preset_config)

        return self.result(f"✅ Preset '{name}' loaded successfully!")

    async def list(self) -> str:
        """List all saved presets."""
        presets = self._list_presets()
        if not presets:
            return self.result("No presets saved yet. Use `/preset save <name>` to create one.")

        lines = ["**Available presets:**\n"]
        for name in presets:
            preset_path = self._get_preset_path(name)
            import yaml
            with preset_path.open() as f:
                data = yaml.safe_load(f)
            desc = data.get("description", "No description")
            lines.append(f"- **{name}**: {desc}")

        return self.result("\n".join(lines))

    async def delete(self, name: str) -> str:
        """Delete a preset."""
        if not name:
            return self.result("Please provide a preset name.", success=False)

        preset_path = self._get_preset_path(name)
        if not preset_path.exists():
            return self.result(f"Preset '{name}' not found.", success=False)

        preset_path.unlink()
        return self.result(f"✅ Preset '{name}' deleted.")

    def _list_presets(self) -> list:
        """List all preset names."""
        if not PRESETS_DIR.exists():
            return []
        return [f.stem for f in PRESETS_DIR.glob("*.yaml")]

    def _redact_sensitive(self, data: dict) -> dict:
        """Redact sensitive information from config."""
        sensitive_keys = ["key", "token", "secret", "password", "auth"]
        result = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = self._redact_sensitive(v)
            elif any(s in k.lower() for s in sensitive_keys):
                result[k] = "***REDACTED***"
            else:
                result[k] = v
        return result

    def _apply_preset(self, preset_config: dict) -> None:
        """Apply preset config to current config (non-destructive merge)."""
        current = core.config.config
        for section, values in preset_config.items():
            if section in current and isinstance(values, dict):
                for key, value in values.items():
                    if value != "***REDACTED***":
                        current[section][key] = value
