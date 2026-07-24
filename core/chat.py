import core
import ulid
import datetime
import os

class Chat:
    def __init__(self, channel):
        self.path = os.path.join("chats", channel.name)
        self.channel = channel

        # Auto-migrate if old format detected
        old_chats_file = core.get_data_path(f"{channel.name}_chats.json")
        if os.path.exists(old_chats_file):
            self._migrate_if_needed()

        self.data = core.storage.StorageList(os.path.join(self.path, "index"), "msgpack")
        self.messages = None # initialized by autoload()

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

    def _migrate_if_needed(self):
        """Automatically migrate old format chat files if detected."""
        import json
        import msgpack
        import shutil
        from pathlib import Path
        
        old_chats_file = core.get_data_path(f"{self.channel.name}_chats.json")
        
        if not os.path.exists(old_chats_file):
            return  # No old format detected
        
        self.channel.log(self.channel.name, f"[MIGRATE] Old format detected for '{self.channel.name}', migrating...")
        
        # Read old chats
        with open(old_chats_file, 'r', encoding='utf-8') as f:
            old_chats = json.load(f)
        
        if not isinstance(old_chats, list):
            self.channel.log(self.channel.name, f"[MIGRATE] Invalid old format, skipping")
            return
        
        # Create new directory structure
        new_channel_dir = core.get_data_path(os.path.join("chats", self.channel.name))
        os.makedirs(new_channel_dir, exist_ok=True)
        os.makedirs(os.path.join(new_channel_dir, "history"), exist_ok=True)
        
        # Migrate each chat
        new_chats = []
        for old_chat in old_chats:
            chat_id = old_chat.get('id', '')
            if not chat_id:
                print(f"skipping {chat_id}")
                continue
            
            # Save messages to separate file
            messages = old_chat.get('messages', [])
            messages_path = os.path.join(new_channel_dir, "history", f"{chat_id}.json")
            with open(messages_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(messages, indent=2, ensure_ascii=False))
            
            # Build new metadata
            new_chats.append({
                "id": chat_id,
                "title": old_chat.get("title", ""),
                "category": old_chat.get("category", "general"),
                "tags": old_chat.get("tags", []),
                "token_usage": old_chat.get("token_usage", 0),
                "metadata": old_chat.get("custom_data", {}),
                "created": old_chat.get("created", ""),
                "updated": old_chat.get("updated", ""),
            })
        
        # Save new index
        index_path = os.path.join(new_channel_dir, "index.mp")
        with open(index_path, 'wb') as f:
            f.write(msgpack.packb(new_chats))
        
        # Handle current chat
        old_current_file = core.get_data_path(f"{self.channel.name}_current_chat")
        if os.path.exists(old_current_file):
            try:
                with open(old_current_file, 'r') as f:
                    current_index = int(f.read().strip())
                safe_index = min(current_index, len(new_chats) - 1) if new_chats else 0
                current_path = os.path.join(new_channel_dir, "current")
                with open(current_path, 'w', encoding='utf-8') as f:
                    f.write(str(safe_index))
            except:
                pass

        # Move old files to backup
        backup_dir = core.get_data_path("chat_migration_backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        # Move chats file
        old_chats_file = core.get_data_path(f"{self.channel.name}_chats.json")
        if os.path.exists(old_chats_file):
            backup_name = f"{self.channel.name}_chats.json.bak"
            shutil.move(old_chats_file, os.path.join(backup_dir, backup_name))
            self.channel.log(self.channel.name, f"[MIGRATE] Backed up old chats file to {backup_name}")
        
        self.channel.log(self.channel.name, f"[MIGRATE] Migrated {len(new_chats)} chats for '{self.channel.name}'")

    async def new(self, category: str = "general", title: str = "", metadata = {}):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        new_id = str(ulid.ULID())[-8:] # so it turns out truncating the ULID from the front can lead to identical id's.. yikes
        self.data.append({
            "id":  new_id,
            "title": title,
            "category": category,
            "tags": [],
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
