import core

class Modules(core.module.Module):
    """Helps your AI manage your modules"""

    settings = {
        "insert_system_prompt": {
            "description": "Whether to insert the list of enabled/disabled modules into the system prompt. Will make the AI aware of what modules are enabled/disabled at all times.",
            "default": True
        },
        "allow_ai_to_toggle": {
            "description": "Allow your AI to enable/disable modules for you. WARNING: very insecure and unsafe when used in public instances! Only use for private instances, and even then, keep the dangers of prompt injection in mind.",
            "default": False,
            "unsafe": True
        }
    }

    async def on_startup(self):
        if not self.config.get("allow_ai_to_toggle"):
            self.disabled_tools.append("toggle")

    async def on_system_prompt(self):
        module_list = {
            "enabled": ", ".join(core.config.get("modules", "enabled", default=[])),
            "disabled": ", ".join(core.config.get("modules", "disabled", default=[]))
        }
        return str(module_list)

    async def toggle(self, name: str):
        if not self.config.get("allow_ai_to_toggle"):
            return self.result("Module toggling is disabled for security. Ask user to manually toggle the module via the web ui or `/config` or by editing the config file.")

        module_name = name.lower().strip()
        if name == "modules":
            return "module manager can only be manually turned off by using the settings dialog, the `/module` command, or editing the config file. user needs to know what you're doing!"

        if await self.manager.toggle_module(name):
            return self.result("Module has been toggled. Remind user to use `/restart` to apply changes")
        else:
            return self.result("That module does not exist!", success=False)

    async def get_help(self, module_name: str):
        """Returns documentation for any given module. Use this if user wants to know how to set up or use a specific module. Prefer over docs_read() for module questions."""

        structure = core.config.get_module_structure()

        if module_name not in structure:
            return self.result("That module does not exist", success=False)

        return structure.get(module_name)
