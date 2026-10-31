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

        # cache system prompt so that it never changes during the course of a chat
        self._cached_system_prompt = None

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
    async def get_system_prompt(self):
        if self._cached_system_prompt:
            # freeze system prompt on chat start,
            # so that the system prompt can never be modified by toolcalls
            # and the changed system prompt will only apply in a new chat
            return self._cached_system_prompt
        
        # only run on_system_prompt if the manager has a channel reference
        if not self.channel:
            return ""

        if self.channel.manager.pure_mode:
            return ""

        system_prompt = []

        active_character = None
        if self.channel:
            active_character = self.get("metadata").get("character")

        # automatically insert system prompts returned by modules (such as memory)
        sysprompt_top = []
        sysprompt_middle = []
        sysprompt_bottom = []

        chan_prompt = await self.channel.on_system_prompt()
        if chan_prompt:
            sysprompt_top.append(f"# Current channel: {self.channel.name}\n{chan_prompt}")

        for module_name, module in self.channel.manager.modules.items():
            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            if module_name in self.channel.manager.broken_modules:
                continue

            char_modules_exempt = ["characters"]
            if (
                self.channel.manager.modules.get("writing_style") and
                self.channel.manager.modules.get("characters") and
                self.channel.manager.modules["characters"].config.get("use_writing_style")
            ):
                char_modules_exempt.append("writing_style")

            if active_character and module_name not in char_modules_exempt and "characters" in self.channel.manager.modules.keys():
                # if a character is currently active, display ONLY the character system prompt
                char_disable_agent_prompts = self.channel.manager.modules["characters"].config.get("disable_agent_prompts_when_character_active")

                if char_disable_agent_prompts:
                    continue

            try:
                module_sysprompt = await module.on_system_prompt()
            except Exception as e:
                self.channel.log("module error", f"{module_name}: in on_system_prompt(): {core.detail_error(e)}")
                self.channel.manager.broken_modules.append(module_name)
                continue

            if module_sysprompt and (module_name not in core.config.get("modules").get("disabled_prompts", [])):
                # default to module name
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "header") and module.header:
                    # but allow overriding the header
                    sysprompt_header = module.header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"

                if module_name in ("agent_framework_awareness", "identity", "memory", "writing_style"):
                    sysprompt_top.append(prompt_chunk)
                elif module_name in ("time", "system"):
                    sysprompt_bottom.append(prompt_chunk)
                else:
                    sysprompt_middle.append(prompt_chunk)

        system_prompt = sysprompt_top+sysprompt_middle+sysprompt_bottom

        if system_prompt:
            sysprompt_str = "\n\n".join(system_prompt)
            self._cached_system_prompt = sysprompt_str
            
            return sysprompt_str
        else:
            return ""

    async def get_end_prompt(self, prevent_recursion=False):
        # only run if the manager has a channel reference
        if not self.channel:
            return None
        
        # don't return endprompt if characters module is active
        active_character = None
        if self.channel:
            active_character = self.get("metadata").get("character")

        # automatically insert system prompts returned by modules (such as memory)
        histend_prompt = []
        for module_name, module in self.channel.manager.modules.items():
            if module_name in self.channel.manager.broken_modules:
                continue

            # if a character is active, use only the character module's endprompt
            if active_character and module_name != "characters":
                continue

            if prevent_recursion and module_name == "token_threshold":
                # if we try to count the system prompt's tokens from the function that counts tokens.. we get recursion
                continue

            if not core.config.get("model").get("use_tools", False) and module_name not in core.modules.nonagentic:
                # skip most prompts if tools are turned off
                continue

            try:
                module_sysprompt = await module.on_end_prompt()
            except Exception as e:
                self.channel.log("module error", f"{module_name}: in on_end_prompt(): {core.detail_error(e)}")
                self.channel.manager.broken_modules.append(module_name)
                continue

            if module_sysprompt:
                sysprompt_header = ' '.join(module_name.split('_')).capitalize()
                if hasattr(module, "header") and module.header:
                    # but allow overriding the header
                    sysprompt_header = module.header
                prompt_chunk = f"# {sysprompt_header}\n{str(module_sysprompt).strip()}"
                histend_prompt.append(prompt_chunk)

        if histend_prompt:
            return "\n\n".join(histend_prompt)
        else:
            return ""
        
    async def _set_current(self, index: int):
        """load a chat and its messages by index"""
        self.current = index

        # store current index into a simple file, for chat autoloading later
        with open(self.current_save_path, "w") as f:
            f.write(str(index))

        # load this chat's Messages object
        self.messages = core.messages.Messages(self.channel, self)

        # let the system prompt be generated anew
        self._cached_system_prompt = None

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
        import sys
        from pathlib import Path
        
        old_chats_file = core.get_data_path(f"{self.channel.name}_chats.json")
        
        if not os.path.exists(old_chats_file):
            return  # No old format detected
        
        print(f"[MIGRATE] Old format detected for '{self.channel.name}', migrating...")

        backup_dir = core.get_data_path("chat_migration_backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        # copy the old chat file to the backup folder
        # but if it fails for ANY reason, inform the user and abort openlumara
        backup_name = f"{self.channel.name}_chats.json.bak"
        backup_path = os.path.join(backup_dir, backup_name)
        
        try:
            shutil.copy2(old_chats_file, backup_path)
            if not os.path.exists(backup_path):
                raise Exception("Backup file not created")
            print(f"[MIGRATE] Backed up old file to {backup_name}")
        except Exception as e:
            self.channel.log("core", f"FATAL ERROR: Could not back up chats file for channel {self.channel.name}. Aborting: {core.detail_error(e)}")
            sys.exit(1)
        
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
                "token_usage_mark": old_chat.get("token_usage_mark", 0),
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

        # and finally, once everything is confirmed safe, remove the old file
        os.remove(old_chats_file)

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
            "token_usage_mark": 0,
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
        
        # reset stored token usage data
        await self.set("token_usage", 0)
        if self.current is not None:
            self.data[self.current]["token_usage_mark"] = 0

        await self.save()

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

    def _history_text(self, chat_id):
        # reads a chat history file and flattens its message contents into one searchable string,
        # cached per-file by mtime so unchanged histories skip re-reading.
        import json

        path = core.get_data_path(os.path.join(self.path, "history", f"{chat_id}.json"))
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return ""

        cached = getattr(self, "_search_history_cache", None)
        if cached is None:
            cached = {}
            self._search_history_cache = cached
        if path in cached and cached[path][0] == mtime:
            return cached[path][1]

        try:
            with open(path, 'r', encoding='utf-8') as f:
                messages = json.load(f)
        except Exception:
            return ""

        parts = []
        for message in messages:
            if message.get("role") == "tool":
                continue

            content = message.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                )

            if isinstance(content, str) and content.strip():
                parts.append(content)

        text = "\n".join(parts)
        cached[path] = (mtime, text)
        return text

    async def search(self, query: str, max_results: int = 100, search_in_content: bool = True):
        """search across all chats for messages matching the query, ranked by core.search (BM25)"""
        if not query or not str(query).strip():
            return []

        entries = []
        metas = {}
        for chat_meta in self.data:
            chat_id = chat_meta.get("id")
            if not chat_id:
                continue

            title = chat_meta.get("title") or ""
            category = chat_meta.get("category") or ""
            text = self._history_text(chat_id) if search_in_content else ""

            if not title and not text:
                continue

            metas[chat_id] = chat_meta
            entries.append({"id": chat_id, "title": title, "category": category, "text": text})

        weights = {"title": 2.0, "category": 1.0}
        if search_in_content:
            weights["text"] = 1.0

        ranked = await core.search.search(entries, query, field_weights=weights, top_n=max_results)

        if not ranked:
            return []

        query_lower = query.strip().lower()
        found_chats = []
        for hit in ranked:
            entry = hit["entry"]
            found = dict(metas[entry["id"]])

            if query_lower and query_lower in (entry.get("title") or "").lower():
                found["title_match"] = True

            if entry.get("text"):
                snippets = core.search.make_snippets(entry["text"], query, max_snippets=3)
                if snippets:
                    found["messages_found"] = len(snippets)
                    found["message_snippets"] = snippets

            found_chats.append(found)

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
