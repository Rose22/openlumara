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

    @core.module.command("load", temporary=True)
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
    async def tag_chat(self, new_name: str, tags: list):
        """lets you rename and tag the current chat"""

        if not new_name:
            return self.result("name must not be blank", False)

        await self.channel.context.chat.set_title(new_name)
        await self.channel.context.chat.set_tags(tags)
        return self.result(f"chat organised!")
