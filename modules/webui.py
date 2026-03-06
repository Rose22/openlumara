import core

class Webui(core.module.Module):
    """
    Allows the AI to manage conversation titles in the WebUI.
    """

    async def rename_conversation(self, new_title: str, conversation_id: str = None):
        """
        Rename a conversation in the WebUI sidebar. Use this to give conversations
        meaningful titles based on their content.

        Args:
            new_title: The new title for the conversation (max 100 chars)
            conversation_id: Optional ID of the conversation to rename.
                If not provided, renames the currently active conversation.
        """

        # Get the webui channel
        webui = None
        for channel_name, channel in self.manager.channels.items():
            if channel_name == "webui":
                webui = channel
                break

        if not webui:
            return self.result("Error: WebUI channel not found", False)

        new_title = new_title.strip()[:100]

        if not new_title:
            return self.result("Error: Title cannot be empty", False)

        conversations = webui.conversations

        # Use provided ID or fall back to current active conversation
        target_id = conversation_id or webui.current_conversation_id

        if not target_id:
            return self.result("Error: No conversation is currently active and no ID was provided", False)

        for i, conv in enumerate(conversations):
            if conv.get('id') == target_id:
                old_title = conv.get('title', 'Untitled')
                conversations[i]['title'] = new_title
                conversations.save()
                return self.result(f"Renamed conversation '{old_title}' to '{new_title}'")

        return self.result(f"Error: Conversation with ID '{target_id}' not found", False)

    async def list_conversations(self):
        """
        List all saved conversations with their IDs and titles.
        Use this to see available conversations before renaming.
        """

        webui = None
        for channel_name, channel in self.manager.channels.items():
            if channel_name == "webui":
                webui = channel
                break

        if not webui:
            return self.result("Error: WebUI channel not found", False)

        conversations = sorted(
            list(webui.conversations),
            key=lambda x: x.get('updated', ''),
            reverse=True
        )

        if not conversations:
            return self.result("No saved conversations found.", False)

        result = "Saved conversations:\n"
        for conv in conversations[:20]: # only the last 20 to avoid overwhelming the AI
            result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')}\n"

        return self.result(result)
