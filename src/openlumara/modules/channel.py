import openlumara.core as core

class Channel(core.module.Module):
    """Inserts channel-specific instructions and prompts into your chats"""

    settings = {
        # "enable_new_user_reminder": {
        #     "description": "This is what makes your AI nag you about checking out the module settings. Turn this off (instead of the entire module) if you want to still be able to ask your AI about how to use openlumara, but without being nagged all the time.. lol",
        #     "default": True
        # },
        "enable_tutorial_prompts": {
            "description": "Whether to insert channel instructions into the system prompt so that your AI can guide you when you're new to OpenLumara. You'll want to turn this off once you're used to openlumara, to save tokens.",
            "default": True
        }
    }

    instructions = {
        "discord": """
            Type `/help` for help. Type `/restart` to restart openlumara. Discord bot can tell who is talking to it if the `enable group chat` setting is turned on, and can show reasoning/thinking if the `show reasoning` setting is turned on.
        """,
        "cli": """
        Type `/help` for help. CLI channel uses python's prompt_toolkit library, and supports common readline keyboard shortcuts. User can use arrow up/down to navigate typing history.
        """,
        "webui":
        """
        Desktop & Mobile:
        - Input bar (at bottom):
            - Press send button or press enter to send message to AI
            - Press upload button to upload a file for the AI to read
        - Top of chat window:
            - Press gear icon to open settings
            - Press icon with arrow down to export chat history
            - Press trashcan icon to clear chat
        - Chat list (hidden behind swipe gesture on mobile, always visible on the left on desktop)
            - Type into search box to search chats within current category
            - Press page icon to search within full content instead of just name
            - Press tag icon to filter by tags
        - Ask AI to rename, tag, or categorize chat (if `chats` module enabled) to auto-sort a chat

        Desktop exclusive:
        - Top of chat window:
            - Click folder icon at top of chat window to open storage editor which lets user view and edit all of openlumara's data files
            - Click keyboard icon or press Ctrl+/ for list of keyboard shortcuts
            - Press Ctrl+Space for Global Search (searches across all chats)
        - Sidebar:
            - Can be hidden using Ctrl+B
            - Split into two columns:
                - Right side (chat list)
                - Left side (category list)
                    - Click category to switch to it
                    - Ask AI to sort chat into a new category to create a new category
                    - Drag and drop a chat from the chat list onto a category to sort it
            - Border between chat list and category list can be clicked to show/hide category list
        - Input bar (at bottom):
            - Press Ctrl+Up and Ctrl+Down to navigate input history
            - You can paste media like photos and screenshots into the input field

        Mobile exclusive:
        - Swipe from left to open menu that contains all previous chats. Tap a chat to switch to it. Tap menu's header to see chat category list.
        """
    }

    async def on_system_prompt(self):
        output = []

        # if self.config.get("enable_new_user_reminder"):
        #
        if not self.channel or await self.channel.context.chat.get_data("character"):
            return None

        chan = core.modules.get_name(self.channel)

        available_chans = core.config.get("channels", "enabled", default=[])

        if chan in ("cli", "matrix"):
            output.append(f"While in the {chan} channel, **DO NOT USE MARKDOWN**.")

        output.append("\nNOTE: if the channel has changed, discard instructions about previous channels.")

        output.append(f"Available channels: {', '.join(available_chans)}")

        if self.config.get("enable_tutorial_prompts") and chan in self.instructions:
            output.append("")
            output.append("Instructions for the user:")
            output.append(self.instructions.get(chan).strip())

        return "\n".join(output)

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
