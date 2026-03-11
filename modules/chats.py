import core

class Chats(core.module.Module):
    @core.module.command("chats")
    async def list(self, args: list):
        """list chats"""

        chats = await self.channel.context.chat.get_all()
        if not chats:
            return self.result("No saved chats found.", False)

        result = f"Saved chats for {self.channel.name}:\n"
        for conv in chats[-20:]: # only the last 20 to avoid overwhelming the AI
            result += f"- [{conv.get('id')}] {conv.get('title', 'Untitled')}\n"

        return result

    @core.module.command("chat")
    async def load(self, args: list):
        """load chat using ID"""
        if not args:
            return "please provide a chat ID"

        result = await self.channel.context.chat.load(args[0])
        if not result:
            return "failed to load chat"
        return "chat loaded"

    @core.module.command("rename")
    async def rename(self, args: list):
        newname = " ".join(args)
        result = await self.channel.context.chat.set_title(newname)
        if not result:
            return "rename failed"
        return f"chat renamed to {newname}"
