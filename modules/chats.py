import core

class Chats(core.module.Module):
    """Lets you or the AI manage your chats"""

    async def get_categories(self):
        cats = [c for c in await self.channel.context.chat.get_categories() if len(c.split(":")) == 1 and c]
        if not cats:
            return self.result("There are no categories yet. Create one!")

        return self.result(cats)

    # AI tool version
    async def organize(self, new_name: str, category: str, tags: list = []):
        """Lets you rename, categorize, and tag the current chat. If the chat fits within an existing category (defined in your system prompt), use that one. If a fitting category does not exist, create a new one."""
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
        """Searches within all previous chats the user ever had with you. Very useful for recalling information from the past! Use only if user explicitly requests it, or if you can't find a past event the user is referring to within your current context!"""
        found = await self._search(query)
        if not found:
            return self.result("no results found")
        return self.result(found)
