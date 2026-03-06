import core

class Modules(core.module.Module):
    async def on_system_prompt(self):
        module_list = {
            "enabled": ", ".join(core.config.get("modules", [])),
            "disabled": ", ".join(core.config.get("modules_disabled", []))
        }
        return str(module_list)

    async def toggle(self, name: str):
        """Toggle a module by name."""

        if name.lower().strip() == "modules":
            return "module manager can only be manually turned off by editing the config file. you need to know what you're doing!"

        module_name = name.lower().strip()

        is_enabled = module_name in core.config.config.get("modules", [])
        is_disabled = module_name in core.config.config.get("modules_disabled", [])

        if not is_enabled and not is_disabled:
            return "module not found"

        if is_enabled:
            core.config.config["modules"].remove(module_name)
            core.config.config["modules_disabled"].append(module_name)
        else:
            core.config.config["modules_disabled"].remove(module_name)
            core.config.config["modules"].append(module_name)

        core.config.config.save()

        if is_enabled:
            return "module disabled. remind user to use /restart to apply changes."
        else:
            return "module enabled. remind user to use /restart to apply changes."

