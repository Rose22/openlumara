import core
import ulid
import datetime
import os
import sys

class Chat:
    def __init__(self, channel):
        self.path = os.path.join("chats", channel.name)
        self.channel = channel

        # Auto-migrate if old format detected
        old_chats_file = core.get_data_path(f"{channel.name}_chats.json")
        if os.path.exists(old_chats_file):
            if not core.proceed_migration:
                print("-"*40)
                print("Found old chat history files! In order for them to work in the new version of openlumara, they need to be migrated.")
                print(f"\033[1;31m!! PLEASE MAKE A BACKUP OF YOUR DATA FOLDER, SO THAT YOU WON'T POTENTIALLY LOSE YOUR CHATS !!\033[0m")
                print()
                if sys.stdin.isatty():
                    print("Then, when you're ready, type MIGRATE in caps into this prompt:")
                    while not core.proceed_migration:
                        confirm = input("migrate?> ")
                        if confirm.strip() == "MIGRATE":
                            core.proceed_migration = True

                        print("Type 'MIGRATE' exactly in capital letters")
                else:
                    print("No terminal detected, auto-migrating (old chats will be backed up).")
                    core.proceed_migration = True
                    
            self._migrate_if_needed()

        self.data = core.storage.StorageList(os.path.join(self.path, "index"), "msgpack")
        self.messages = None # initialized by autoload()

        # store currently loaded chat index
        self.current = None
        self.current_save_path = core.get_data_path(os.path.join(self.path, f"current"))

    async def autoload(self):
        """loads the last used chat if applicable, otherwise it creates a new chat. basically the class's async constructor"""
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

    # ------------------
    # helper functions
    # ------------------
    async def _set_current(self, index: int):
        """load a chat and its messages by index"""
        self.current = index

        # store current index into a simple file, for chat autoloading later
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
        
        print(f"[MIGRATE] Old format detected for '{self.channel.name}', migrating...")
        
        # Read old chats
        with open(old_chats_file, 'r', encoding='utf-8') as f:
            old_chats = json.load(f)
        
        if not isinstance(old_chats, list):
            print(f"[MIGRATE] Invalid old format, skipping")
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
            print(f"[MIGRATE] Backed up old chats file to {backup_name}")
        
        print(f"[MIGRATE] Migrated {len(new_chats)} chats for '{self.channel.name}'")

    async def update_timestamp(self):
        if self.current is None:
            raise Exception("No chat is currently loaded!")

        now = datetime.datetime.utcnow().isoformat()
        self.data[self.current]["updated"] = now
        await self.save()

    # ------------------
    # Chat Manipulation
    # ------------------
    async def new(self, category: str = "general", title: str = "New chat", metadata = None):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        if metadata is None:
            metadata = {}

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

        # initialize token usage count using estimated count from the context class
        await self.set("token_usage", await self.channel.context.get_total_tokens())

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

        # remove the chat history file
        messages_path = core.get_data_path(os.path.join(
            "chats",
            self.channel.name,
            "history",
            f"{id}.json"
        ))
        try:
            os.remove(messages_path)
        except FileNotFoundError:
            pass

        # and remove it from the index file
        self.data.pop(index)
        self.data.save()

        # Adjust current index if needed
        if self.current is not None:
            if self.current == index:
                if self.data:
                    # that means we've deleted the current chat
                    await self._set_current(min(index, len(self.data) - 1))
                else:
                    # we've ended up with blank data.. so autocreate a new one!
                    await self.autoload()
            elif self.current > index:
                # Current was after deleted item, shift down
                await self._set_current(self.current-1)

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

        if index is None:
            raise Exception("tried to load a blank chat id!")

        if self.current == index:
            # silently allow it
            return False

        await self._set_current(index)

        # start a prompt warmup using this chat's data
        # try:
        #     await self.channel.manager.API.start_prompt_warmup(context=await self.channel.context.get(), notify=core.debug)
        # except Exception as e:
        #     self.channel.log("core", f"failure while sending prompt warmup to API: {core.detail_error(e)}")

        return True

    # ----------------
    # Data Retrieval
    # ----------------
    async def export(self):
        """exports the current chat to a file"""

        if self.current is None:
            raise Exception("No chat is currently loaded!")

        turns = await self.channel.turncollector.group_history(await self.messages.get())

        turn_export = []
        for turn in turns:
            turn_lines = []
            turn_lines.append(f"--- {turn.get('role')} ---")

            # extract content
            items = []
            for message in turn.get("messages"):
                role = message.get("role")
                content = message.get("content")
                toolcalls = message.get("tool_calls")

                # handle content
                if content and role != "tool" and not toolcalls:
                    if isinstance(content, str):
                        items.append(('content', content.strip()))
                    elif isinstance(content, list):
                        for part in content:
                            if part.get("type") == "text":
                                items.append(('content', part.get('text').strip()))
                
                # handle toolcalls
                if toolcalls:
                    for toolcall in toolcalls:
                        items.append(('tool', self.channel.tc_manager.display_call(toolcall)))

            # group items by type
            blocks = []
            current_block_type = None
            current_block_items = []

            for item_type, item_content in items:
                if item_type != current_block_type:
                    # Type changed, save previous block
                    if current_block_items:
                        blocks.append(current_block_items)
                    current_block_type = item_type
                    current_block_items = []
                current_block_items.append(item_content)
            
            # don't forget the last block
            if current_block_items:
                blocks.append(current_block_items)

            # join blocks with double newlines, items within blocks with single newlines
            formatted_blocks = ["\n".join(block) for block in blocks]
            turn_lines.append("\n\n".join(formatted_blocks))

            turn_export.append("\n".join(turn_lines))

        return "\n\n".join(turn_export)


    def get(self, key = None, default = None, index = None):
        if self.current is None and not index:
            raise Exception("No chat is currently loaded!")

        if index is None:
            index = self.current

        # return the chat itself if chat.get() is called without a key
        if key is None:
            return self.data[index]

        # otherwise, get the chat's requested value
        if key in self.data[index].keys():
            return self.data[index][key]
        else:
            return default

    async def search(self, query: str, max_results: int = 100):
        """search across all chats for messages matching the query"""
        import json
        
        results = []
        query_lower = query.lower()
        
        found_chats = []
        for chat_meta in self.data:
            found = dict(chat_meta)

            chat_id = chat_meta.get("id")
            if not chat_id:
                continue
            
            if query_lower in chat_meta.get("title").lower():
                found["title_match"] = True
            
            # Load messages from the history file
            history_path = core.get_data_path(os.path.join(self.path, "history", f"{chat_id}.json"))
            if not os.path.exists(history_path):
                if found.get("title_match"):
                    found_chats.append(found)
                continue
            
            try:
                with open(history_path, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
            except (json.JSONDecodeError, Exception):
                if found.get("title_match"):
                    found_chats.append(found)
                continue
            
            # Search through messages
            found_messages = []
            for msg_index, message in enumerate(messages):
                content = message.get("content", "")
                if not content:
                    continue
                
                # Handle multimodal content - extract text parts
                if isinstance(content, list):
                    content = " ".join(
                        part.get("text", "") 
                        for part in content 
                        if isinstance(part, dict) and part.get("type") == "text"
                    )
                
                if not isinstance(content, str) or not content.strip():
                    continue
                
                # Case-insensitive substring search
                if query_lower in content.lower():
                    # Find the match position for snippet generation
                    match_pos = content.lower().find(query_lower)
                    
                    # Generate snippet with context
                    snippet_start = max(0, match_pos - 50)
                    snippet_end = min(len(content), match_pos + len(query) + 50)
                    snippet = content[snippet_start:snippet_end]
                    
                    # Add ellipsis if truncated
                    if snippet_start > 0:
                        snippet = "..." + snippet
                    if snippet_end < len(content):
                        snippet = snippet + "..."
                    
                    found_messages.append(snippet)
            
            if found_messages:
                found.update({
                    "messages_found": len(found_messages),
                    "message_snippets": found_messages
                })
                found_chats.append(found)
                    
            if len(found_chats) >= max_results:
                return found_chats

        # Sort with priority: title matches first, then content-only matches
        # Within each group, sort by updated date descending
        # Use stable sort: first by date descending, then by title_match (True first)
        found_chats.sort(key=lambda x: x["updated"] or "", reverse=True)
        found_chats.sort(key=lambda x: not x.get("title_match"))  # not True=False=0 sorts before not False=True=1
        
        return found_chats

    async def set(self, key, value, index = None):
        if self.current is None and not index:
            raise Exception("No chat is currently loaded!")

        if index is None:
            index = self.current

        if key in self.data[index].keys():
            self.data[index][key] = value
            return True
        
        raise Exception(f"{key} is not a valid chat property")

    def get_all(self):
        """returns all chats in the storage, sorted by updated date (most recent first)"""
        return sorted(self.data, key=lambda c: c.get("updated", ""), reverse=True)

    def get_categories(self):
        collected_categories = []
        for chat in self.data:
            if chat.get("category") not in collected_categories:
                collected_categories.append(chat.get("category"))
        return collected_categories
