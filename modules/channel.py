import core

class Channel(core.module.Module):
    async def on_system_prompt(self):
        if not self.channel:
            return None

        if await self.channel.context.chat.get_data("character"):
            # don't add this to the system prompt if a character from the character module is active
            return None

        chan = core.module.get_name(self.channel)
        chan_instr = None
        match chan:
            case "cli":
                chan_instr = "type /help for help. /stop is not available here."
            case "webui":
                chan_instr = """
Type /help for help.

Features only available while channel is WebUI:

## On mobile
- User can press the hamburger button (on the top left) or swipe from the left to open the sidebar

## On desktop
- User can press Ctrl+B to toggle the sidebar.
- User can press ctrl+/ to see keyboard shortcuts
- User can press Ctrl+Space to open a global search (searches within all past chats)

## On both mobile & desktop
- User can press the gear icon at the top of the screen to open the settings.
- User can press the icon with a down arrow to export chats
- User can type text in the sidebar to search in conversations, use the icon next to the search box in the sidebar to toggle searching within conversation content instead of title.
- User can click or tap the `filter by tag` header in the sidebar to select tags to filter by.
- User can stop text generation by pressing the stop button, or typing /stop.
                """.strip()
            case "discord":
                chan_instr = "say `/help` to me for a list of commands."
            case _:
                pass

        if chan_instr:
            chan_instr = f"instructions for user: {chan_instr}\n\nNOTE: if the channel has changed, discard instructions about previous channels."

        return chan_instr

    async def on_end_prompt(self):
        if not self.channel:
            return None

        chan = core.module.get_name(self.channel)
        chan_transl = {
            "cli": "Command Line Interface (CLI)",
            "webui": "WebUI",
            "discord": "Discord"
        }

        chan_display = chan_transl.get(chan, chan)
        # wow confusing syntax lol. return channel name if couldnt get translation by using name as key

        return f"current channel: {chan_display}"
