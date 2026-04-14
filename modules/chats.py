import core

class Chats(core.module.Module):
    """manage your chat history"""

    async def on_system_prompt(self):
        categories = await self.channel.context.chat.get_categories()
        if len(categories) <= 1:
            return None

        filtered_categories = []
        for index, category in enumerate(categories):
            # get rid of special categories
            if len(category.split(":")) > 1:
                continue

            if not category:
                # if we somehow end up with a blank category.. filter it out
                continue

            filtered_categories.append(category)

        return f"Available categories to categorise chat into: {', '.join(filtered_categories)}"

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
            result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')[:50]}\n"

        return result

    @core.module.command("chat", temporary=True, help={
        "": "show information about current chat",
        "<ID>": "load chat using its ID",
        "rename <new_name>": "rename chat to <new_name>",
        "category <category>": "put chat in category <category>"
    })
    async def load(self, args: list):
        """load chat using its ID"""
        if not args:
            chat_title = await self.channel.context.chat.get_title()
            chat_category = await self.channel.context.chat.get_category()
            chat_tags = await self.channel.context.chat.get_tags()
            chat_tags_str = "None"
            if chat_tags:
                chat_tags_str = ", ".join(chat_tags)
            chat_data = await self.channel.context.chat.get_data() or {}
            if chat_data:
                chat_data_str = "\n"
                chat_data_str += "\n".join([f"  {key}: {value}" for key, value in chat_data.items()])
            else:
                chat_data_str = "None"

            return f"== chat info ==\ntitle: {chat_title}\ncategory: {chat_category}\ntags: {chat_tags_str}\ndata: {chat_data_str}"

        match args[0].lower().strip():
            case "rename":
                newname = " ".join(args[1:])
                result = await self.channel.context.chat.set_title(newname)
                if not result:
                    return "rename failed"
                return f"chat renamed to {newname}"
            case "category":
                newcat = " ".join(args[1:])
                result = await self.channel.context.chat.set_category(newcat)
                if not result:
                    return "setting category failed"
                return f"chat categorised into {newcat}"
            case _:
                result = await self.channel.context.chat.load(args[0])
                if not result:
                    return "failed to load chat"
                return "chat loaded"

    # AI tool version
    async def organize(self, new_name: str, category: str, tags: list = []):
        """
        Lets you rename, categorize, and tag the current chat.

        If the chat fits within an existing category (defined in your system prompt), use that one.
        If a fitting category does not exist, create a new one.
        """

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
            if chat.get("title", "").lower().strip().find(query.lower().strip()) != -1:
                found = True

            # search within content
            for message in chat.get("messages", []):
                content = message.get("content", "")
                if not isinstance(content, str):
                    continue

                if content.lower().find(query.lower().strip())!= -1:
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
        """Searches within your chat history"""
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
        Use only if user explicitely requests it, or if you can't find a past event the user is referring to within your current context!
        """
        found = await self._search(query)
        if not found:
            return self.result("no results found")
        return self.result(found)
