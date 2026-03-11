import core

class Modules(core.module.Module):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._header = "modules"

    async def on_system_prompt(self):
        module_list = {
            "enabled": ", ".join(core.config.get("modules").get("enabled", [])),
            "disabled": ", ".join(core.config.get("modules").get("disabled", []))
        }
        return str(module_list)

    async def toggle(self, name: str):
        """Toggle a module by name."""

        if name.lower().strip() == "modules":
            return "module manager can only be manually turned off by editing the config file. you need to know what you're doing!"

        module_name = name.lower().strip()

        is_enabled = module_name in core.config.config.get("modules").get("enabled", [])
        is_disabled = module_name in core.config.config.get("modules").get("disabled", [])

        if not is_enabled and not is_disabled:
            return "module not found"

        if is_enabled:
            core.config.config["modules"]["enabled"].remove(module_name)
            core.config.config["modules"]["disabled"].append(module_name)
        else:
            core.config.config["modules"]["disabled"].remove(module_name)
            core.config.config["modules"]["enabled"].append(module_name)

        core.config.config.save()

        if is_enabled:
            return "module has been disabled. remind user to use /restart to apply changes."
        else:
            return "module has been enabled. remind user to use /restart to apply changes."

