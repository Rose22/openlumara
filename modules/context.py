import core

class Context(core.module.Module):
    """Helps you manage your context window"""

    @core.module.command("sysprompt", temporary=True)
    async def show_sysprompt(self, args):
        """shows only the system prompt"""

        if not core.config.get("api").get("context_window", True):
            return "CONTEXT DISABLED"

        _sysprompt = await self.channel.manager.get_system_prompt()
        if not _sysprompt:
            _sysprompt = "BLANK"
        sysprompt = f"=== system prompt ===\n{_sysprompt}"
        disabled_prompts = core.config.get("modules").get("disabled_prompts")
        if disabled_prompts:
            sysprompt += "\n\n=== disabled prompts ===\n"
            sysprompt += "\n".join([mod_name for mod_name in disabled_prompts])
        endprompt = await self.channel.manager.get_end_prompt()
        if endprompt:
            sysprompt += f"\n\n=== end prompts ===\n{endprompt}"

        return sysprompt if sysprompt else "BLANK"

    @core.module.command("context", temporary=True, help={
        "": "show current context window",
        "full": "show context window including system prompt",
        "raw": "show context as raw JSON"
    })
    async def show_context(self, args):
        """shows current context window"""

        if not core.config.get("api").get("context_window", True):
            return "CONTEXT DISABLED"

        show_system_prompt = True if len(args) and args[0] == "full" else False

        context = await self.channel.context.get(system_prompt=show_system_prompt)
        if not context:
            return "BLANK"

        if len(args) and args[0] == "raw":
            import json
            return json.dumps(context, indent=2)

        context_display = []

        for message in context:
            content = message.get("content")
            if not content:
                if message.get("tool_calls"):
                    content = str(message.get("tool_calls"))

            context_display.append(f"== {message.get('role')} ==\n{content}")

        context_display.append("---")

        disabled_prompts = core.config.get("modules").get("disabled_prompts")
        if disabled_prompts:
            disabled_prompts_str = "\n".join([mod_name for mod_name in disabled_prompts])
            context_display.append(f"== disabled prompts ==\n{disabled_prompts_str}")

        ctx_string = ""
        context_size = await self.channel.context.get_size()
        for key, value in context_size.items():
            ctx_string += f"{key}: {value}\n"
        context_display.append(f"== context size ==\n{ctx_string}")

        return "\n\n".join(context_display)

    @core.module.command("prompts", temporary=True)
    async def show_prompts(self, args):
        """show which prompts are active"""

        enabled = []
        no_prompt = []
        disabled = []
        for module_name, module in self.channel.manager.modules.items():
            has_sysprompt = True if await module.on_system_prompt() else False

            if has_sysprompt and (module_name not in core.config.get("modules").get("disabled_prompts")):
                enabled.append(module_name)
            elif module_name not in core.config.get("modules").get("disabled_prompts"):
                no_prompt.append(module_name)
            else:
                disabled.append(module_name)

        enabled_str = "\n".join(enabled)
        no_prompt_str = "\n".join(no_prompt)
        disabled_str = "\n".join(disabled)
        return f"== modules with active prompts ==\n{enabled_str}\n\n== modules that don't include prompts ==\n{no_prompt_str}\n\n== modules with disabled prompts ==\n{disabled_str}"
