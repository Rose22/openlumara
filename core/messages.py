import core
import os
import asyncio

class Messages:
    def __init__(self, channel, chat):
        self.channel = channel
        self.chat = chat

        chat_id = self.chat.get("id")
        if not isinstance(chat_id, str):
            raise Exception("Could not load chat messages: Chat ID must be a string")

        self.path = os.path.join(self.chat.path, "history", self.chat.get("id"))
        # compact_json: history is rewritten on every save, so skip indent + ascii escaping
        self.data = core.storage.StorageList(self.path, "json", compact_json=True)

        # saves are debounced: rapid adds (tool call chains, streams) coalesce
        # into a single disk write instead of one full rewrite per message
        self._save_task = None
        self.SAVE_DEBOUNCE_SECONDS = 0.15

    def _schedule_save(self):
        if self._save_task and not self._save_task.done():
            return
        self._save_task = asyncio.create_task(self._debounced_save())

    async def _debounced_save(self):
        await asyncio.sleep(self.SAVE_DEBOUNCE_SECONDS)
        self._save_task = None
        await self.save()

    async def save(self):
        """flush any pending debounced save immediately, then write to disk"""

        task, self._save_task = self._save_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        await self.chat.update_timestamp()
        return self.data.save()

    async def get(self, index = None):
        """get message history of current chat"""
        # allow targeting a specific index
        if index is not None:
            if index >= len(self.data):
                raise Exception("Invalid message index")

            return self.data[index]

        # if no index is specified, just return the entire message history
        return self.data

    async def add(self, message: dict, cmd=False, ghost = False):
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

        # if marked as a ghost message, set the flag. gets handled in self.trim()
        # ghost messages are invisible to the AI
        if ghost:
            new_message["_metadata"]["ghost"] = True

        if cmd:
            # if the message is a command (or command response), mark it as such
            new_message["_metadata"]["is_cmd"] = True

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
                new_message["_metadata"]["injection"] = "\n\n".join(injections)

        self.data.append(new_message)
        self._schedule_save()
        return True

    async def edit(self, index: int, message):
        """edit message by its index"""
        if index >= len(self.data):
            return False

        self.data[index] = message
        await self.save()

    async def delete(self, index: int):
        """delete message from current chat"""
        self.data.pop(index)
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

        self.data.load(new_messages)
        await self.save()
        return True

    async def clear(self):
        self.data.clear()
        # persist the wipe: without a save here the old history file would
        # resurrect the messages on the next restart
        await self.save()
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