import core

class Chats(core.module.Module):
    """manage your chat history"""

    @core.module.command("new", temporary=True)
    async def new_chat(self, args):
        """starts a new session"""
        result = await self.channel.context.chat.new()
        if result:
            return "New session started."
        else:
            return "Failed to start new session"

    @core.module.command("clear")
    async def clear_chat(self, args):
        """clear chat history"""

        result = await self.channel.context.chat.clear()
        if result:
            return "Chat history wiped."
        else:
            return "Failed to wipe chat history"

    @core.module.command("chats", temporary=True)
    async def _list(self, args: list):
        # if i overwrite the list builtin, it leads to really bad stuff

        """list chats"""

        chats = await self.channel.context.chat.get_all()
        if not chats:
            return self.result("No saved chats found.", False)

        result = f"Saved chats for {self.channel.name}:\n"
        for conv in chats[-20:]: # only the last 20 to avoid overwhelming the AI
            result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')}\n"

        return result

    @core.module.command("chat", temporary=True)
    async def load(self, args: list):
        """load chat using its ID"""
        if not args:
            return "please provide a chat ID"

        print(args[0])
        result = await self.channel.context.chat.load(args[0])
        if not result:
            return "failed to load chat"
        return "chat loaded"

    @core.module.command("rename")
    async def cmd_rename(self, args: list):
        """rename current chat"""

        newname = " ".join(args)
        result = await self.channel.context.chat.set_title(newname)
        if not result:
            return "rename failed"
        return f"chat renamed to {newname}"

    # AI tool version
    async def tag_chat(self, new_name: str, category: str, tags: list):
        """lets you rename, categorize, and tag the current chat"""

        if not new_name:
            return self.result("name must not be blank", False)

        await self.channel.context.chat.set_title(new_name)
        await self.channel.context.chat.set_category(category)
        await self.channel.context.chat.set_tags(tags)
        return self.result(f"chat organised!")

    async def _search(self, query: str):
        chats = await self.channel.context.chat.get_all()
        if not chats:
            return False

        found_chats = []
        for index, chat in enumerate(chats):
            # do not search within current chat
            if index == 0 or index == len(chats)-1:
                continue

            # create a new chat dict so that we can include only the messages that contain the query
            filtered_chat = {"id": chat.get("id"), "title": chat.get("title"), "tags": chat.get("tags", []), "messages": []}
            found = False

            # search within title
            if chat.get("title", "").find(query) != -1:
                found = True

            # search within content
            for message in chat.get("messages", []):
                if message.get("content", "").find(query) != -1:
                    filtered_chat["messages"].append({"role": message.get("role"), "content": message.get("content")})
                    found = True

            if found:
                found_chats.append(filtered_chat)

        if not found_chats:
            return False

        return found_chats

    # command version
    @core.module.command("search", temporary=True)
    async def cmd_search(self, args: list):
        """searches within your chat history"""
        query = " ".join(args)
        found = await self._search(query)
        if not found:
            return "no results found"

        output = "" if not found else f"Found these chats containing '{query}':\n\n"
        for chat in found:
            output += f"[{chat.get('id')}] {chat.get('title')}\n"

        return output

    # AI tool version
    async def search(self, query: str):
        """
        Searches within all previous chats the user ever had with you. very useful for recalling information from the past!

        IMPORTANT: When user asks about things that happened before the current chat, search your chat history.
        """
        found = await self._search(query)
        if not found:
            return self.result("no results found")
        return self.result(found)
