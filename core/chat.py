import core
import ulid
import datetime
import os

class Chat:
    def __init__(self, channel):
        self.path = os.path.join("chats", channel.name)
        self.data = core.storage.StorageList(os.path.join(self.path, "index"), "msgpack")
        self.messages = None # initialized by autoload()
        self.channel = channel

        # store currently loaded chat index
        self.current = None
        self.current_save_path = core.get_data_path(os.path.join(self.path, f"current"))

    async def autoload(self):
        # chat autoresume
        if os.path.exists(self.current_save_path) and core.config.get("core", {}).get("auto_resume_chats"):
            try:
                with open(self.current_save_path, "r") as f:
                    target_index = int(f.read())

                if target_index < len(self.data):
                    await self._set_current(target_index)
                    return
            except Exception as e:
                self.channel.log_error("couldn't autoresume chat", e)

        # create a new chat if one wasn't found
        await self.new()

    async def _set_current(self, index: int):
        self.current = index

        # store current index into a simple file
        with open(self.current_save_path, "w") as f:
            f.write(str(index))

        # load this chat's Messages object
        self.messages = core.messages.Messages(self.channel, self)

    def _find_index(self, id: str):
        """find index of the chat with that ID"""
        for index, chat in enumerate(self.data):
            if chat.get("id", "").upper() == id.upper():
                return index

        return None

    async def new(self, category: str = "general", title: str = "", metadata = {}):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        new_id = str(ulid.ULID())[-8:] # so it turns out truncating the ULID from the front can lead to identical id's.. yikes
        self.data.append({
            "id":  new_id,
            "title": title,
            "category": category,
            "tags": [],
            "messages": [],
            "token_usage": 0,
            "metadata": metadata,
            "created": now,
            "updated": now
        })

        index = len(self.data) - 1
        await self._set_current(index)
        await self.set("token_usage", 0)

        self.data.save()

        # start a system prompt warmup so that the response is instant (if the user types slowly... lol)
        #await self.channel.manager.API.start_prompt_warmup(notify=core.debug)

        return new_id

    async def clear(self):
        if self.current is None:
            raise Exception("No chat is currently loaded!")

        await self.messages.clear()
        
        # Reset token_usage since we're clearing the chat
        # API token usage is only valid for the exact context that was sent
        await self.set("token_usage", 0)
        
        await self.save()

        # start a system prompt warmup so that the response is instant (if the user types slowly... lol)
        #await self.channel.manager.API.start_prompt_warmup(notify=core.debug)

        return True

    async def delete(self, id: str):
        """delete an entire chat"""

        index = self._find_index(id)
        if index is None:
            return False

        await self.messages.clear()
        self.data.pop(index)
        self.data.save()

        # Adjust current index if needed
        if self.current is not None:
            if self.current == index:
                # Deleted the current chat - reset or move to previous
                await self._set_current(min(index, len(self.data) - 1) if self.data else None)
            elif self.current > index:
                # Current was after deleted item, shift down
                self.current -= 1

        # start a prompt warmup using this chat's data
        # try:
        #     await self.channel.manager.API.start_prompt_warmup(context=await self.channel.context.get(), notify=core.debug)
        # except Exception as e:
        #     self.channel.log("core", f"failure while sending prompt warmup to API: {core.detail_error(e)}")

        return self.current

    async def save(self):
        if self.current is None:
            await self.new()

        return self.data.save()

    async def load(self, id: str):
        index = self._find_index(id)

        if index is None or self.current == index:
            return False

        await self._set_current(index)

        # start a prompt warmup using this chat's data
        # try:
        #     await self.channel.manager.API.start_prompt_warmup(context=await self.channel.context.get(), notify=core.debug)
        # except Exception as e:
        #     self.channel.log("core", f"failure while sending prompt warmup to API: {core.detail_error(e)}")

        return True

    def get(self, key = None):
        if self.current is None:
            raise Exception("No chat is currently loaded!")

        if key is None:
            return self.data[self.current]

        if key in self.data[self.current].keys():
            return self.data[self.current][key]
        else:
            return {}
        
        raise Exception(f"{key} is not a valid chat property")
    async def set(self, key, value):
        if self.current is None:
            raise Exception("No chat is currently loaded!")

        if key in self.data[self.current].keys():
            self.data[self.current][key] = value
            return True
        
        raise Exception(f"{key} is not a valid chat property")

    def get_all(self):
        """returns all chats in the storage"""
        return self.data

    def get_categories(self):
        collected_categories = []
        for chat in self.data:
            if chat.get("category") not in collected_categories:
                collected_categories.append(chat.get("category"))
        return collected_categories
