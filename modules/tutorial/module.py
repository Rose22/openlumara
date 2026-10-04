import core

class Tutorial(core.module.Module):
    """Guides you through openlumara if you're new!"""

    async def on_system_prompt(self):
        output = []

        disable_instr = "by typing `/module tutorial`"
        webui_instr = ""
        if "webui" in self.manager.channels:
            webui_url = self.manager.channels["webui"].url

            webui_instr = f"""
Ask the user if they need any help with setting up openlumara. If user says yes, follow these instructions: To set up openlumara, the user needs to open the webui's settings dialog (gear icon at the top of the chat window in the webUI). If the user is not currently in the webUI, tell them to open the webUI at `{webui_url}`. Then inside the settings dialog, the most important thing is that the user can toggle channels and modules, and set up settings to their liking per channel and per module. Also, ask the user if they would like to explore the openlumara documentation with you to learn the ins and outs of how to use openlumara.
            """.strip()
            disable_instr += " or through the WebUI's settings dialog, in the Modules section"

        output.append(f"""
ALWAYS upon the first message of a conversation, tell the user how to use openlumara by referencing the channel instructions within your system prompt. Present the information in a user-friendly, easy to understand way.

The `docs` module is active by default and gives you access to documentation to answer any questions the user might have about openlumara! If user asks any questions about openlumara that are not covered by this prompt, use the docs module to get documentation about it. For module-specific questions, use modules_get_help instead.

Tell the user with extra emphasis and attention-grabbing emojis that this tutorial message can be turned off by disabling the tutorial module, which the user can do {disable_instr}.

Further, tell the user:
- Modules can insert system prompts like this tutorial, add new commands for the user to use, do things when the user or the AI sends a message, run anything in the background, and other cool stuff.
- `/new` creates a new chat, which they can easily load later by using `/chats` and then using the chat's ID like `/chat your_id_here`.
- `/stop` forcibly cancels whatever the AI is doing.
- `/compress` will compress the context by asking the AI to summarize. you never truly lose your chat history because it uses a special "cutoff signal" message, which in the webUI will look like a dotted line. You can revert the compression by deleting a message above the dotted line.
- `/config` can be used to change settings without using the webUI or manually editing the config file. `/config` by itself will show all available categories, from there it's just a matter of drilling down.. e.g. `/config modules` will show all available modules, `/config modules writing_style` will show all available settings for that module. `/config modules writing_style vocabulary_level` shows the value of that module setting. `/config modules writing_style vocabulary_level simple` sets that module's vocabulary_level setting to simple. usually, after changing a setting with `/config`, a `/restart` is required to apply the settings.

{webui_instr}
""")

        return "\n".join(output)
