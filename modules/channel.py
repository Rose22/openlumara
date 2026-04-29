import core

class Channel(core.module.Module):
    """Inserts channel-specific instructions and prompts into your chats"""

    async def on_system_prompt(self):
        if not self.channel or await self.channel.context.chat.get_data("character"):
            return None
        chan = core.modules.get_name(self.channel)
        note = "\n\nNOTE: if the channel has changed, discard instructions about previous channels."
        if chan == "cli":
            return f"While in cli channel, **DO NOT USE MARKDOWN**. Format every response in plaintext! Type /help for help. /stop is not available here.{note}"
        if chan == "webui":
            short = core.config.get("channels", {}).get("settings", {}).get("webui", {}).get("use_short_replies")
            style = "\nWhile in webui channel, write replies as if texting. Keep it short and conversational." if short else ""
            return f"{style}\n\nInstructions for user:\nType /help for help.\n\nWebUI Features:\n- Mobile: Swipe/hamburger for sidebar. Gear icon for settings. Down arrow to export. Search in sidebar or conversation content.\n- Desktop: Ctrl+B toggle sidebar, ctrl+/ shortcuts, Ctrl+Space global search. Folder icon for Storage Editor. Click edges to show/hide panels.\n- Both: Upload files via upload button. Stop generation with /stop or stop button.{note}"
        if chan in ("telegram", "discord", "matrix"):
            nomarkdown = "While in this channel, **DO NOT USE MARKDOWN**." if chan == "matrix" else ""
            chat_style = "Write replies as if texting. Keep it short and conversational."
            return f"{nomarkdown}\n{chat_style}\n\nType /help for help. Type /stop to stop generation anytime!{note}"
        return None

    async def on_end_prompt(self):
        if not self.channel:
            return None

        chan = core.modules.get_name(self.channel)
        chan_transl = {
            "cli": "Command Line Interface (CLI)",
            "webui": "WebUI",
            "discord": "Discord",
            "telegram": "Telegram",
            "matrix": "Matrix"
        }

        chan_display = chan_transl.get(chan, chan)
        # wow confusing syntax lol. return channel name if couldnt get translation by using name as key

        return f"current channel: {chan_display}"
