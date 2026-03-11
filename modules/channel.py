import core

class Channel(core.module.Module):
    async def on_system_prompt(self):
        if not self.channel:
            return None

        chan = core.module.get_name(self.channel)
        chan_instr = None
        match chan:
            case "cli":
                chan_instr = "type /help for help. /stop is not available here."
            case "webui":
                chan_instr = "type /help for help. features only available while channel is WebUI: press the gear icon at the top of the screen to open the settings. press the icon with a down arrow to export chats. on mobile, press the hamburger button (on the top left) or swipe from the left to open the sidebar. on desktop, the sidebar is always visible on the left. type text in the sidebar to search in conversations, use the icon next to the search box in the sidebar to toggle searching within conversation content instead of title. click or tap the `filter by tag` header in the sidebar to select tags to filter by. user can stop text generation by pressing the stop button, or typing /stop. user can press ctrl+/ to see keyboard shortcuts)."
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
