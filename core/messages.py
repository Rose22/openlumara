import core
import os

class Messages:
    def __init__(self, channel, chat):
        self.channel = channel
        self.chat = chat

        self.path = os.path.join(self.chat.path, "history", self.chat.get("id"))
        self.data = core.storage.StorageList(self.path, "json")

        # for index in range(len(self.data) - 1, -1, -1):
        #     chat = self.data[index]
        #     messages = chat.get("messages", [])
            
        #     # find any blank chats and delete them
        #     if not messages:
        #         self.data.pop(index)
        #     # find chats that only contain command/responses and delete them
        #     elif self._is_command_only(messages):
        #         self.data.pop(index)
        #     # find any missing metadata fields and add them
        #     else:
        #         for key, default_value in self.DEFAULT_DATA.items():
        #             if key not in chat.keys():
        #                 self.data[index][key] = default_value

    async def save(self):
        """just an alias for save() on the data"""
        return self.data.save()

    async def get(self, index = None):
        """get message history of current chat"""
        if index:
            if index > len(self.data):
                raise Exception("Invalid message index")

            return self.data[index]

        return self.data

    async def add(self, message: dict, cmd=False, ghost = False):
        """add message to current chat"""
        # make a copy so we don't modify the original reference
        new_message = message.copy()

        if not self.chat.get("title"):
            # auto-set title
            msg_content = self.channel._extract_content(new_message)
            if isinstance(msg_content, str):
                await self.chat.set("title", msg_content[:100]+".." if len(msg_content) > 100 else msg_content)
            else:
                # this happens when the user uploads a media file. don't set that as a title, lol
                pass

        # if marked as a ghost message, set the flag. gets handled in self.trim()
        # ghost messages are invisible to the AI
        if ghost:
            new_message["ghost"] = True

        if cmd:
            # if the message is a command (or command response), mark it as such
            new_message["is_cmd"] = True

        # inject any special messages coming from on_message_inject() in modules, such as timestamps
        injections = []
        if message.get("role") == "user":
            for module_name, module in self.channel.manager.modules.items():
                if hasattr(module, 'on_message_inject'):
                    try:
                        injection = await module.on_message_inject()
                        if injection:
                            injections.append(injection)
                    except Exception as e:
                        self.channel.log("module error", f"{module.name}: in on_message_inject(): {core.detail_error(e)}")

            if injections:
                new_message["injection"] = "\n\n".join(injections)

        self.data.append(new_message)

        index = len(self.data) - 1
        await self.save()
        return True
    
    async def edit(self, index: int, message):
        """edit message by its index"""
        if index >= len(self.data):
            return False

        self.data[index] = message
        await self.save()

    async def delete(self, index: int = None):
        """delete message from current chat"""
        if index is None:
            index = -1

        self.data.pop(index)
        index = len(self.data) - 1
        await self.save()

        return index

    async def delete_from(self, index: int):
        """
        Deletes all messages below a certain index
        """
        if index > len(self.data):
            raise Exception("Invalid message index")

        # return all messages up to and including the target message
        new_messages = self.data[:index+1]

        self.data = new_messages
        return True

    async def get_last_message_with_role(self, role: str, cutoff_index: int = None):
        # get last message by that role

        # if we have a "cutoff index",
        # it means we have to search backwards
        # from that index
        # which is very useful for, say,
        # regenerating a message
        # because we can target the last user message
        # before the cutoff index

        if len(self.data) == 1:
            # just return the first index
            return 0

        if cutoff_index is not None:
            start_index = cutoff_index
        else:
            # Start at the very end
            start_index = len(self.data)

        for index in range(start_index, -1, -1):
            if index >= len(self.data):
                continue

            message = self.data[index]
            if message.get("role") == role:
                return index

        return -1
