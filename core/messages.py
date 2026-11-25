import core
import os
import time

class Messages:
    def __init__(self, channel, chat):
        self.channel = channel
        self.chat = chat

        chat_id = self.chat.get("id")
        if not isinstance(chat_id, str):
            raise Exception("Could not load chat messages: Chat ID must be a string")

        self.path = os.path.join(self.chat.path, "history", self.chat.get("id"))
        self.data = core.storage.StorageList(self.path, "json")

        # whether to use indentation in the json or not (saves disk space)
        self.data.pretty = False

        # bumped on every mutation of the history, for use with caching
        self.revision = 0

        # lowest message index touched by an edit/delete since the last
        # grouping; None means every change since then was a pure append
        self.mutated_below = None

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

    def note_mutation_at(self, index: int):
        """forces the turn group cache to refresh from (index) onward"""
        if self.mutated_below is None or index < self.mutated_below:
            self.mutated_below = index

    async def save(self):
        """saves data and updates the chat's timestamp"""

        await self.chat.update_timestamp()
        # history dump on a worker thread: a big chat's serialization must
        # never block the event loop (streams included)
        return await self.data.save_async()

    async def get(self, index = None):
        """get message history of current chat"""
        # allow targeting a specific index
        if index is not None:
            if index >= len(self.data):
                raise Exception("Invalid message index")

            return self.data[index]

        # if no index is specified, just return the entire message history
        return self.data

    async def add(self, message: dict, cmd=False, ghost = False, hide = False):
        """add message to current chat"""
        # make a copy so we don't modify the original reference
        new_message = message.copy()
        if "_metadata" not in new_message.keys():
            new_message["_metadata"] = {}

        if (not self.chat.get("title") or self.chat.get("title") == "New chat") and message.get("role") == "user" and not cmd:
            # auto-set title (if the message was not a command)
            msg_content = self.channel._extract_content(new_message)
            if isinstance(msg_content, str):
                await self.chat.set("title", msg_content[:100]+".." if len(msg_content) > 100 else msg_content)
            else:
                # this happens when the user uploads a media file. don't set that as a title, lol
                pass

        # add current time as a timestamp to the message, so that it can be displayed in channels
        new_message["_metadata"]["timestamp"] = int(time.time())

        # if marked as a ghost message, set the flag. gets handled in self.trim()
        # ghost messages are invisible to the AI
        if ghost:
            new_message["_metadata"]["ghost"] = True

        # use the hide flag to hide messages from the UI. needs to be implemented by a channel, most included channels support it
        if hide:
            new_message["_metadata"]["hide"] = True

        if cmd:
            # if the message is a command (or command response), mark it as such
            new_message["_metadata"]["is_cmd"] = True

        # inject any special messages coming from on_message_inject() in modules, such as timestamps
        injections = []
        if message.get("role") == "user":
            for module_name, module in self.channel.manager.modules.items():
                if hasattr(module, 'on_message_inject'):
                    try:
                        injection = await module.on_message_inject(new_message.get("content"))
                        if injection:
                            injections.append(injection)
                    except Exception as e:
                        self.channel.log("module error", f"{module.name}: in on_message_inject(): {core.detail_error(e)}")

            if injections:
                new_message["_metadata"]["injection"] = "\n\n".join(injections)

        # this is the point where it's safe to auto-compact
        if message.get("role") == "user" and not cmd:
            if await self.channel.context.is_over_threshold():
                await self.channel.context.compress()

        self.data.append(new_message)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Gufo) :: (2026-11-24) harness:openlumara
        self.revision += 1

        index = len(self.data) - 1
        await self.save()
        return True

    async def edit(self, index: int, message):
        """edit message by its index"""
        if index >= len(self.data):
            return False

        self.data[index] = message
        self.revision += 1

        self.note_mutation_at(index)
        await self.save()

    async def delete(self, index: int):
        """delete message from current chat"""
        self.note_mutation_at(index)

        self.data.pop(index)
        self.revision += 1
        index = len(self.data) - 1
        await self.save()

        return index

    async def delete_from(self, index: int):
        """
        Deletes the message at the given index and all messages after it
        """
        if index >= len(self.data):
            raise Exception("Invalid message index")

        # return all messages up to (but not including) the target message
        new_messages = self.data[:index]

        self.note_mutation_at(index)

        self.data.load(new_messages)
        self.revision += 1
        await self.save()
        return True

    async def clear(self):
        self.note_mutation_at(0)

        self.data.clear()
        self.revision += 1
        return True

    async def get_last_message_with_role(self, role: str, cutoff_index: int = None):
        """gets the latest message with the specified role"""

        # if we have a "cutoff index",
        # it means we have to search backwards
        # from that index
        # which is very useful for, say,
        # regenerating a message
        # because we can target the last user message
        # before the cutoff index

        if not self.data:
            return -1

        if len(self.data) == 1:
            # just return 0 if there is only one message... but only if the role matches the request
            if self.data[0].get("role") == role:
                return 0
            return -1

        if cutoff_index is not None:
            # clamp it
            start_index = min(cutoff_index, len(self.data) - 1)
        else:
            start_index = len(self.data) - 1

        for index in range(start_index, -1, -1):
            if self.data[index].get("role") == role:
                return index

        return -1
