import core
import json
import os
import shutil
import sys
import channels.webui.api as webui

class Characters(core.module.Module):
    """Lets your AI embody different characters! inspired by characterAI, janitorAI, sillytavern, etc."""

    category = "creative"

    settings = {
        "enable_character_awareness": {
            "default": True,
            "description": "Put the list of stored characters into the system prompt so that the AI always knows what characters it can switch to"
        },
        "system_prompt": {
            "type": "long_text",
            "description": "An optional prompt that gets inserted before the character prompt, to instruct the AI on how to behave in character mode. Use for jailbreaking and so on. Leave blank to disable.",
            "default": ""
        },
        "your_name": {
            "description": "The name characters will use to refer to you",
            "default": "User"
        },
        "your_profile": {
            "type": "long_text",
            "description": "Describe yourself here. Stuff like your appearance, what you like and dislike, hobbies, etc. Just an overall profile of yourself. The AI will see this so that every character knows who you are!",
            "default": ""
        },
        "enabled_modules": {
            "default": [],
            "type": "list",
            "description": "Module names whose tools and system prompts stay available while a character in Character mode is active. For example: web_search. Characters set to Assistant mode are never restricted",
        },
        "use_first_messages": {
            "description": "Whether a character's first message gets sent automatically when switching to that character in an empty chat",
            "default": True
        },
        "use_writing_style": {
            "description": "Whether to use the writing style defined by the `writing style` module for characters. This will add that module's prompt to the character prompt even if agent prompts are disabled, making all your characters use your preferred writing style setup",
            "default": True
        },
        "category": {
            "description": "Category that new chats created from the characters sidebar get placed in",
            "default": "general"
        }
    }

    header = "Character"

    async def on_ready(self):
        self.characters = core.storage.StorageDict("characters", type="json_folder")

        self._migrate_if_needed()
        self._ingest_pngs()
        self._normalize_all()
        
        if self.config.get("enable_character_awareness"):
            # disable character listing tool
            self.disabled_tools.append("get_all")

    def character_mode(self, name):
        """the mode of a stored character: Character (default) or Assistant.
        used by core/chat.py to decide whether to suppress other modules' prompts"""
        char = self._find_character(name)
        if not char:
            return "Character"
        return char.get("mode") or "Character"

    def _apply_tool_mode(self, char):
        """sets the channel's tool availability for the active character's mode.
        char is the resolved character dict, or None when no character is active.
        Assistant characters (and no character at all) keep everything; Character
        mode keeps only the enabled modules' tools"""
        if char is None or char.get("mode") == "Assistant":
            self.channel.force_disable_tools = False
            self.channel.override_tools = None
            return

        enabled = [
            str(m).strip().lower()
            for m in (self.config.get("enabled_modules") or [])
            if str(m).strip()
        ]

        tools = [
            entry["tool"]
            for entry in self.channel.tool_loader.catalog.values()
            if entry["module"] in enabled
        ]

        if not tools:
            # nothing enabled (or no enabled name matched a loaded tool): full
            # tool blackout. this has to go through force_disable_tools, because
            # an empty override list is falsy and would fall back to the full set.
            self.channel.force_disable_tools = True
            self.channel.override_tools = None
        else:
            self.channel.force_disable_tools = False
            self.channel.override_tools = tools

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
    # Migration from the old single-file characters.json to folder storage, following the same safety protocol as core/chat.py:
    # mandatory backup (abort on failure), convert, verify on disk, only then remove the old file.
    def _migrate_if_needed(self):
        """migrates the old single-file characters.json into the folder storage, if it exists"""
        old_file = core.get_data_path("characters.json")
        if not os.path.exists(old_file):
            return

        folder = self.characters.path
        if os.path.exists(folder) and any(f.endswith(".json") for f in os.listdir(folder)):
            core.log("warning", "old characters.json found but folder storage already contains characters, skipping migration")
            return

        print("[MIGRATE] Old single-file character storage detected, migrating...")

        backup_dir = core.get_data_path("character_migration_backups")
        os.makedirs(backup_dir, exist_ok=True)

        # copy the old file to the backup folder
        # but if it fails for ANY reason, inform the user and abort openlumara
        backup_path = os.path.join(backup_dir, "characters.json.bak")
        try:
            shutil.copy2(old_file, backup_path)
            if not os.path.exists(backup_path):
                raise Exception("Backup file not created")
            print(f"[MIGRATE] Backed up old character storage to {backup_path}")
        except Exception as e:
            core.log("error", f"FATAL ERROR: could not back up characters.json before migrating. Aborting: {core.detail_error(e)}")
            sys.exit(1)

        try:
            with open(old_file, "r", encoding="utf-8") as f:
                old_chars = json.load(f)
        except Exception as e:
            core.log("error", f"could not read old character storage, leaving it in place: {core.detail_error(e)}")
            return

        if not isinstance(old_chars, dict):
            core.log("error", "old character storage is not a dict, leaving it in place")
            return

        migrated = {}
        for name, char in old_chars.items():
            normalized = self._normalize_character(name, char)
            if not normalized:
                core.log("warning", f"skipping unreadable character '{name}' during migration (preserved in backup)")
                continue
            migrated[name] = normalized

        self.characters.update(migrated)
        self.characters.save()

        # only remove the old file once the new storage is confirmed on disk
        try:
            written = [f for f in os.listdir(folder) if f.endswith(".json")]
        except OSError:
            written = []

        if len(written) < len(migrated):
            core.log("error", "migration verification failed, old characters.json left in place")
            return

        os.remove(old_file)
        print(f"[MIGRATE] migrated {len(migrated)} characters to folder storage")

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-06) harness:openlumara
    def _normalize_world_info(self, world_info):
        """converts old dict-based world info into the list-of-dicts format"""
        if isinstance(world_info, dict):
            # sillytavern character books store their entries dict under 'entries'
            if isinstance(world_info.get("entries"), (dict, list)):
                raw_entries = world_info["entries"]
                if isinstance(raw_entries, dict):
                    raw_entries = list(raw_entries.values())
            else:
                # plain {keyword: info} dict
                raw_entries = {k: {"key": k, "content": v} for k, v in world_info.items()}

            entries = []
            for entry in raw_entries:
                if not isinstance(entry, dict):
                    continue
                info = entry.get("content") or entry.get("info")
                keywords = entry.get("key") or entry.get("keywords")
                if not info or not keywords:
                    continue
                if isinstance(keywords, str):
                    keywords = [k.strip() for k in keywords.split(",") if k.strip()]
                entries.append({"keywords": keywords, "info": str(info).strip()})
            return entries

        if isinstance(world_info, list):
            # repair list entries that came in as plain strings or a string keyword
            entries = []
            for entry in world_info:
                if not isinstance(entry, dict):
                    continue
                if not entry.get("info"):
                    continue
                keywords = entry.get("keywords")
                if isinstance(keywords, str):
                    entry["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]
                elif not keywords:
                    continue
                entries.append(entry)
            return entries

        return []

    def _normalize_character(self, stored_key, char):
        """converts a character of any supported format into openlumara's flat internal format"""
        if not isinstance(char, dict):
            return None

        if "profile" in char:
            # already internal format; just make sure every field exists
            return {
                "name": char.get("name") or stored_key,
                "category": char.get("category"),
                "profile": char.get("profile", ""),
                "first_message": char.get("first_message", ""),
                "world_info": self._normalize_world_info(char.get("world_info")),
                "mode": char.get("mode") or "Character"
            }

        # character card V2 wraps everything in a data field, V1 is flat
        card = char.get("data", char)
        if not isinstance(card, dict):
            return None

        name = card.get("name") or stored_key
        profile = card.get("description", "")

        if not profile:
            # legacy openlumara format used 'identity' as its profile field
            profile = char.get("identity", "")

        if not profile:
            return None

        # fold personality and example conversations into the profile,
        # since openlumara has no dedicated prompt slots for them
        extras = []
        if card.get("personality"):
            extras.append(f"Personality: {card['personality']}")
        if card.get("mes_example"):
            extras.append(f"Example conversation:\n{card['mes_example']}")
        if card.get("scenario"):
            extras.append(f"Scenario:\n{card['scenario']}")
        if extras:
            profile = profile + "\n\n" + "\n\n".join(extras)

        return {
            "name": name,
            "category": char.get("category"),
            "profile": profile,
            "first_message": card.get("first_mes", char.get("first_message", "")),
            "world_info": self._normalize_world_info(card.get("world_info") or card.get("character_book") or []),
            "mode": char.get("mode") or "Character"
        }

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
    # Picks up character cards dropped into the characters folder as PNG files by reading the base64 JSON
    # embedded in their tEXt/iTXt metadata chunks (the way sillytavern-style cards store them).
    def _extract_card_from_png(self, png_path):
        """extracts an embedded character card from a png's metadata chunks, returns a dict or None"""
        import struct
        import base64
        import zlib

        try:
            fd = core.sandbox_open(os.path.dirname(png_path), os.path.basename(png_path), os.O_RDONLY)
            with os.fdopen(fd, "rb") as f:
                if f.read(8) != b"\x89PNG\r\n\x1a\n":
                    return None

                while True:
                    header = f.read(8)
                    if len(header) < 8:
                        break

                    length, chunk_type = struct.unpack(">I4s", header)
                    data = f.read(length)
                    f.read(4)  # crc, we don't verify it

                    if chunk_type not in (b"tEXt", b"iTXt"):
                        if chunk_type == b"IEND":
                            break
                        continue

                    keyword, _, remainder = data.partition(b"\x00")
                    if keyword not in (b"chara", b"ccv2"):
                        continue

                    if chunk_type == b"iTXt":
                        # compression flag, compression method, language tag, translated keyword
                        compressed = remainder[0] if remainder else 0
                        remainder = remainder[3:]
                        remainder = remainder.partition(b"\x00")[2]
                        remainder = remainder.partition(b"\x00")[2]
                        if compressed == 1:
                            remainder = zlib.decompress(remainder)

                    decoded = base64.b64decode(remainder).decode("utf-8")
                    card = json.loads(decoded)
                    if isinstance(card, dict):
                        return card
        except Exception:
            return None

        return None

    def _ingest_pngs(self):
        """converts any card-pngs in the characters folder into regular json characters"""
        folder = self.characters.path
        if not os.path.exists(folder):
            return

        changed = False
        for filename in core.sandbox_listdir(folder):
            if not filename.lower().endswith(".png"):
                continue

            card = self._extract_card_from_png(os.path.join(folder, filename))
            if not card:
                continue

            name = filename[:-4]
            normalized = self._normalize_character(name, card)
            if not normalized or not normalized.get("profile"):
                core.log("warning", f"png '{filename}' had no usable character card, skipping")
                continue

            if not normalized.get("name"):
                normalized["name"] = name

            # don't overwrite an existing character with the same name
            if self._find_character(normalized["name"]):
                continue

            self.characters[normalized["name"]] = normalized
            changed = True

        if changed:
            self.characters.save()

    def _normalize_all(self):
        """normalizes all stored characters, so manually dropped-in card files also work"""
        changed = False
        for name, char in list(self.characters.items()):
            normalized = self._normalize_character(name, char)
            if not normalized:
                continue
            if normalized != char:
                self.characters[name] = normalized
                changed = True

        if changed:
            self.characters.save()

    @core.module.command("characters")
    async def _list_characters(self, args: list = []):
        """list all your characters"""

        # collect categories
        if not self.characters:
            return "You have no characters yet"

        sorted_by_cat = {}
        for character_name, character in self.characters.items():
            category = character.get("category", None)

            if category:
                if category not in sorted_by_cat.keys():
                    sorted_by_cat[category] = []

                sorted_by_cat[category].append(character_name)
            else:
                if "unsorted" not in sorted_by_cat.keys():
                    sorted_by_cat["unsorted"] = []

                sorted_by_cat["unsorted"].append(character_name)

        char_list = []
        for category_name, category in sorted_by_cat.items():
            if not category:
                # autoremove empty categories
                if category_name in self.characters.keys():
                    del(self.characters[category_name])

            characters = ", ".join(category)
            char_list.append(f"{category_name}: {characters}")

        characters = "\n".join(char_list)
        return characters

    @core.module.tool
    async def get_all(self):
        return self.result(await self._list_characters())

    @core.module.command("character", help={
        "": "show current character",
        "<name>": "switch to character <name>",
        "reset": "switch to default AI assistant character"
    })
    async def cmd_switch(self, args: list):
        name = " ".join(args)
        if not name:
            char = self.channel.context.chat.get("metadata").get("character")
            if char:
                return f"currently active character: {char}"
            else:
                return "please provide a character name."
        elif name in("reset", "default"):
                self.channel.context.chat.get("metadata")["character"] = ""
                self._apply_tool_mode(None)
                return "character has been reset to default"

        character = self._find_character(name)
        if not character:
            return f"character {name} does not exist!"

        char_name = self._find_char_name(name)

        await self.switch(char_name)

        first_msg = character.get("first_message", "")
        if first_msg and self.config.get("use_first_messages"):
            first_msg = self._replace_tags(char_name, first_msg)
            return f"character switched to {char_name}\n\n{first_msg}"

        return f"character switched to {char_name}"

    async def on_system_prompt(self):
        curr_char = self.channel.context.chat.get("metadata").get("character")
        char = self._find_character(curr_char) if curr_char else None

        # if the character was deleted (or the metadata holds a stale/invalid
        # value), clean it up so the rest of the prompt isn't broken
        if curr_char and not char:
            self.channel.context.chat.get("metadata")["character"] = ""
            curr_char = ""

        self._apply_tool_mode(char if curr_char else None)

        tool_text = f"Characters available to switch yourself to:\n{await self._list_characters()}" if (
            core.config.get("model", {}).get("use_tools") and
            self.config.get("enable_character_awareness") and
            not curr_char
        ) else ""

        if not curr_char:
            return tool_text or None

        char_name = char.get("name", curr_char)
        char_profile = char.get("profile", "")

        if not char_profile:
            return "Failed to extract character profile from character data"

        char_scenario = char.get("scenario", "")

        # replace tags such as {{user}} and {{char}}
        char_profile = self._replace_tags(char_name, char_profile)
        if char_scenario:
            char_scenario = self._replace_tags(char_name, char_scenario)

        # imported cards can contain escaped newlines, restore them
        char_profile = char_profile.replace("\\n", "\n")
        if char_scenario:
            char_scenario = char_scenario.replace("\\n", "\n")

        character_text_build = []
        character_text_build.append(f"## You: {char_name}\n{char_profile}")

        if char_scenario:
            character_text_build.append(f"## Scenario\n{char_scenario}")

        user_profile = self.config.get("your_profile").strip()
        if user_profile:
            user_name = self.config.get("your_name").strip()
            character_text_build.append(f"## The user: {user_name}\n{self._replace_tags(char_name, user_profile)}")

        char_text = "\n\n".join(character_text_build)

        # if this is an empty chat, insert the first message into history by sending it as a push
        first_msg = char.get("first_message", "")
        if self.config.get("use_first_messages") and first_msg:
            if len(await self.channel.context.chat.messages.get()) == 0:
                first_msg = self._replace_tags(char_name, first_msg)
                await self.channel.push({"role": "assistant", "content": first_msg})

        system_prompt = self.config.get("system_prompt", "")
        if system_prompt: system_prompt = system_prompt+"\n\n"
        return system_prompt+char_text

    async def on_message_inject(self, user_message: str):
        curr_char_name = self.channel.context.chat.get("metadata").get("character")
        if not curr_char_name:
            return None

        char = self._find_character(curr_char_name)

        output = ""
        for entry in char.get("world_info") or []:
            # multiple keywords per world info entry
            for keyword in entry.get("keywords") or []:
                if keyword.lower().strip() in user_message.lower().strip():
                    info = entry.get("info")
                    output += f"{keyword}: {info}\n"
                    break

        return output or None

    @core.module.tool
    async def switch(self, name: str):
        """Switches you to a different character. This will change your personality! Use this if user requests it."""
        char = self._find_character(name)
        if not char:
            return self.result("character not found", False)

        # prefer the canonical stored key so on_system_prompt() can always
        # resolve the character reliably, regardless of how it was invoked
        char_name = self._find_char_name(name) or char.get("name")

        self.channel.context.chat.get("metadata")["character"] = char_name

        # allow system prompt to be regenerated
        self.channel.context.chat._cached_system_prompt = None

        self._apply_tool_mode(char)

        first_msg = char.get("first_message", "")
        if first_msg and self.config.get("use_first_messages"):
            # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
            # option B: never push mid-toolcall (pushes race with live stream rendering and
            # corrupt message ordering). instead instruct the model to stream the greeting
            # itself as its final response, so it flows through the normal display pipeline.
            first_msg = self._replace_tags(char_name, first_msg)
            return self.result(
                f"Switched to {char_name}. "
                f"Begin your reply now with this exact greeting, verbatim, and add nothing else:\n\n{first_msg}"
            )

        return self.result(f"Switch successful. Write your response as the character's first message.")

    @core.module.tool
    async def switch_to_default(self):
        """Switches you back to your default identity."""
        self.channel.context.chat.get("metadata")["character"] = ""

        # allow system prompt to be regenerated
        self.channel.context.chat._cached_system_prompt = None

        self._apply_tool_mode(None)

        return "success"

    def _case_insensitive_replace(self, text, old, new):
        """Replaces all occurrences of 'old' with 'new' in 'text', ignoring case."""
        if not old:
            return text

        # Convert both text and old substring to lowercase for searching
        lower_text = text.lower()
        lower_old = old.lower()

        result_parts = []
        index = 0
        old_len = len(old)

        while True:
            # Find the next occurrence of the lowercase substring
            found_index = lower_text.find(lower_old, index)

            if found_index == -1:
                # No more matches, append the rest of the string
                result_parts.append(text[index:])
                break

            # Append the text segment before the match (preserving original case)
            result_parts.append(text[index:found_index])
            # Append the new replacement
            result_parts.append(new)

            # Move the index forward to continue searching
            index = found_index + old_len

        return "".join(result_parts)

    def _find_character(self, name: str):
        """searches for a character, case insensitive"""

        for character_name, character in self.characters.items():
            if character_name.lower().strip() == name.lower().strip():
                return character
        return None

    def _find_char_name(self, name: str):
        """searches for a character and returns the full name with correct case"""
        for character_name, character in self.characters.items():
            if character_name.lower().strip() == name.lower().strip():
                return character_name

    def _replace_tags(self, name: str, character: str):
        """replaces the magic words defined in the character card spec with their appropriate replacements"""
        user_name = self.config.get("your_name")
        replacement_map = {
            "{{char}}": name,
            "{char}": name,
            "<BOT>": name,
            "{{user}}": user_name,
            "{user}": user_name,
            "<USER>": user_name
        }

        for word, replacement in replacement_map.items():
            character = self._case_insensitive_replace(character, word, replacement)

        return character

    @core.module.tool
    async def add(self, name: str, profile: str, category: str = "", mode: str = "Character"):
        """
        Adds a new character to your character storage.

        Note: new characters are created without a first message. If the user
        wants one, they can add it later with edit().

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            category: Category to organize the character under. Optional.
            mode: Character (pure roleplay: only the character prompt stays, tools limited to the enabled modules) or Assistant (full system prompt and all tools). Optional, defaults to Character.
        """
        if not name.strip():
            return self.result("character name cannot be empty", False)

        exists = self._find_character(name)
        if exists:
            return self.result("character already exists", False)

        if not profile:
            return self.result("character profile must not be blank.")

        self.characters[name] = {
            "name": name,
            "category": category or None,
            "profile": profile,
            "first_message": "",
            "world_info": [],
            "mode": mode or "Character"
        }
        self.characters.save()
        return self.result("character added")

    @core.module.tool
    async def edit(self, name: str, profile: str = None, category: str = None, first_message: str = None, mode: str = None):
        """
        Edits an existing character. All fields except name are optional.

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            category: Category to organize the character under
            first_message: The first message the character will send when starting a new chat.
            mode: Character (pure roleplay) or Assistant (full system prompt and all tools). Optional.
        """
        if not name.strip():
            return self.result("character name cannot be empty", False)

        char = self._find_character(name)
        if not char:
            return self.result("character doesn't exist!", False)

        # always write back to the canonical (stored) key so we don't
        # accidentally create a duplicate entry with different casing
        canonical_name = self._find_char_name(name)

        # we're using `is not None` because we need to retain the ability
        # to set stuff to blank strings
        self.characters[canonical_name] = {
            "name": canonical_name,
            "category": category if category is not None else char.get("category"),
            "profile": profile if profile is not None else char.get("profile", ""),
            "first_message": first_message if first_message is not None else char.get("first_message", ""),
            "world_info": char.get("world_info", []),
            "mode": mode or char.get("mode") or "Character"
        }
        self.characters.save()
        return self.result("character edited")

    @core.module.tool
    async def read(self, name: str):
        """
        Reads a character profile.
        DO NOT use if trying to read the character you're currently switched to!
        ALWAYS use before editing a character!
        """
        character = self._find_character(name)
        if not character:
            return "character does not exist!"

        return self.result(character)

    @core.module.tool
    async def delete(self, name: str):
        """Deletes a character. Use ONLY if user explicitly requests it."""
        name = self._find_char_name(name)

        if name in self.characters.keys():
            self.characters.pop(name, None)
            self.characters.save()
            return self.result(f"character {name} deleted")

        return self.result("character doesn't exist!", False)

    @core.module.tool
    async def import_json(self, json_code: str):
        """imports a character card (spec V1 or V2) into your character storage"""
        try:
            char_obj = json.loads(json_code)
        except Exception as e:
            return self.result(f"error: {core.detail_error(e)}", success=False)

        if not isinstance(char_obj, dict) or not char_obj:
            return self.result("error: character card was empty", success=False)

        normalized = self._normalize_character("", char_obj)
        if not normalized or not normalized.get("name") or not normalized.get("profile"):
            return self.result("error: failed to extract a usable name and profile from this character card", success=False)

        # re-importing an existing character updates it in place
        existing_name = self._find_char_name(normalized["name"])
        name = existing_name or normalized["name"]

        self.characters[name] = normalized
        self.characters.save()

        return self.result("character successfully imported")

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-03)
    # webui extension routes (reference implementation for the @webui.route
    # convention, see channels/webui/api.py). handlers are private methods so
    # the tool loader ignores them; they forward to the existing tool methods
    # and pass their self.result() dicts through untouched - the webui
    # forwarder unwraps those into the standard api envelope.
    # reachable at /api/ext/characters/<path>

    @webui.route("list")
    async def _route_list(self, body=None, query=None):
        """compact character list grouped by category, for pickers/UIs"""
        grouped = {}
        for name, char in self.characters.items():
            category = char.get("category") or "general"
            grouped.setdefault(category, []).append({
                "name": char.get("name") or name,
                "tags": char.get("tags") or [],
            })
        return {
            "categories": [
                {"name": cat, "characters": sorted(chars, key=lambda c: c["name"].lower())}
                for cat, chars in sorted(grouped.items())
            ]
        }

    @webui.route("current")
    async def _route_current(self, body=None, query=None):
        """name of the character active in the current chat, or null"""
        return self.channel.context.chat.get("metadata").get("character") or None

    @webui.route("get")
    async def _route_get(self, body=None, query=None):
        name = (query or {}).get("name", "")
        char = self._find_character(name)
        if not char:
            return self.result("character not found", success=False)
        return self.result(char)

    @webui.route("switch", method="POST")
    async def _route_switch(self, body=None, query=None):
        name = (body or {}).get("name", "")
        if not name:
            return self.result("error: no character name given", success=False)
        return await self.switch(name)

    @webui.route("switch_default", method="POST")
    async def _route_switch_default(self, body=None, query=None):
        await self.switch_to_default()
        return self.result("switched to default character")

    @webui.route("delete", method="POST", admin_only=True)
    async def _route_delete(self, body=None, query=None):
        name = (body or {}).get("name", "")
        char = self._find_character(name)
        if not char:
            return self.result("character not found", success=False)
        stored_key = self._find_char_name(name)
        del self.characters[stored_key]
        self.characters.save()
        return self.result(f"deleted character {stored_key}")

    @webui.route("import", method="POST", admin_only=True)
    async def _route_import(self, body=None, query=None):
        json_code = (body or {}).get("json_code", "")
        if isinstance(json_code, (dict, list)):
            json_code = json.dumps(json_code)
        return await self.import_json(json_code)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-14)
    # CRUD + file-import routes backing the character management modal
    # (webui/templates/modals/manage_characters.html).

    @webui.route("remove", method="POST", admin_only=True)
    async def _route_remove(self, body=None, query=None):
        return await self.delete(str((body or {}).get("name", "")))

    @webui.route("all")
    async def _route_all(self, body=None, query=None):
        """full character list for the management modal, sorted by name"""
        chars = []
        for key, char in self.characters.items():
            chars.append({
                "key": key,
                "name": char.get("name") or key,
                "category": char.get("category") or "",
                "profile": char.get("profile", ""),
                "first_message": char.get("first_message", ""),
                "world_info": char.get("world_info"),
                "mode": char.get("mode") or "Character"
            })
        chars.sort(key=lambda c: c["name"].lower())
        return chars

    def _clean_tags(self, raw):
        """tags arrive from the form as a comma-separated string (or a list)"""
        if raw is None:
            return []
        if isinstance(raw, str):
            return [t.strip() for t in raw.split(",") if t.strip()]
        if isinstance(raw, list):
            return [str(t).strip() for t in raw if str(t).strip()]
        return []

    @webui.route("add", method="POST", admin_only=True)
    async def _route_add(self, body=None, query=None):
        body = body or {}
        name = str(body.get("name", "")).strip()
        profile = str(body.get("profile", "")).strip()

        if not name:
            return self.result("character name cannot be empty", success=False)
        if not profile:
            return self.result("character profile must not be blank", success=False)
        if self._find_character(name):
            return self.result("a character with that name already exists", success=False)

        self.characters[name] = {
            "name": name,
            "category": str(body.get("category", "")).strip() or None,
            "profile": profile,
            "first_message": str(body.get("first_message", "")),
            "world_info": self._normalize_world_info(body.get("world_info")),
            "mode": body.get("mode") or "Character"
        }
        self.characters.save()
        return self.result(f"character {name} added")

    @webui.route("edit", method="POST", admin_only=True)
    async def _route_edit(self, body=None, query=None):
        body = body or {}
        # 'key' is the canonical storage key (sent by the modal); 'name' is
        # the new name, which may differ -> rename
        key = self._find_char_name(str(body.get("key", "")))
        if not key:
            return self.result("character not found", success=False)

        new_name = str(body.get("name", "")).strip()
        profile = str(body.get("profile", "")).strip()

        if not new_name:
            return self.result("character name cannot be empty", success=False)
        if not profile:
            return self.result("character profile must not be blank", success=False)

        # renaming onto another existing character would clobber it
        clash = self._find_char_name(new_name)
        if clash and clash.lower() != key.lower():
            return self.result("a character with that name already exists", success=False)

        self.characters[key] = {
            "name": new_name,
            "category": str(body.get("category", "")).strip() or None,
            "profile": profile,
            "first_message": str(body.get("first_message", "")),
            "world_info": self._normalize_world_info(body.get("world_info")),
            "mode": body.get("mode") or "Character"
        }

        # rename: re-key the storage entry. save() prunes the old key's
        # json file itself, so no manual file cleanup is needed here.
        if new_name != key:
            self.characters[new_name] = self.characters.pop(key)

            # chats reference characters by their stored key, so re-stamp
            # any chat that used the old one (best effort: the current
            # chat is a live object and persists on its next save)
            for chat in self.channel.context.chat.get_all():
                meta = chat.get("metadata") or {}
                if meta.get("character") == key:
                    meta["character"] = new_name

        self.characters.save()
        return self.result("character edited")

    @webui.route("import_file", method="POST", admin_only=True)
    async def _route_import_file(self, body=None, query=None):
        """imports a character card from a file the browser read locally.
        json -> parse and normalize; png -> extract the embedded card from
        the tEXt/iTXt metadata chunks (sillytavern-style cards)."""
        filename = str((body or {}).get("filename", "")).strip()
        data_b64 = str((body or {}).get("data", ""))
        if not filename or not data_b64:
            return self.result("error: no file data received", success=False)

        # strip a data-URL prefix if the browser sent one
        if "," in data_b64 and data_b64.strip().startswith("data:"):
            data_b64 = data_b64.split(",", 1)[1]

        lower = filename.lower()

        if lower.endswith(".json"):
            import base64
            try:
                json_code = base64.b64decode(data_b64).decode("utf-8")
            except Exception as e:
                return self.result(f"error: could not decode file: {core.detail_error(e)}", success=False)
            return await self.import_json(json_code)

        if lower.endswith(".png"):
            import base64
            import tempfile
            try:
                raw = base64.b64decode(data_b64)
            except Exception as e:
                return self.result(f"error: could not decode file: {core.detail_error(e)}", success=False)

            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    tmp_path = tmp.name
                    tmp.write(raw)

                card = self._extract_card_from_png(tmp_path)
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

            if not card:
                return self.result("error: no character card found inside this png", success=False)

            name = filename[:-4].strip()
            normalized = self._normalize_character(name, card)
            if not normalized or not normalized.get("profile"):
                return self.result("error: failed to extract a usable name and profile from this png", success=False)

            if not normalized.get("name"):
                normalized["name"] = name

            # re-importing an existing character updates it in place
            existing_name = self._find_char_name(normalized["name"])
            key = existing_name or normalized["name"]

            self.characters[key] = normalized
            self.characters.save()
            return self.result("character successfully imported")

        return self.result("error: unsupported file type, use .json or .png", success=False)

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-04)
    # chat helpers for the characters sidebar panel. the earlier attempt at
    # character-scoped twins of /api/chats/days|day|tags|search was dropped:
    # the tabbed-sidebar design makes them pointless (the panel keeps its
    # own flat chat list, no need to mirror core's day-group machinery),
    # and they referenced helpers nested inside create_fastapi() anyway.

    def _chat_character(self, chat):
        """the character key stored in a chat's metadata, '' when none"""
        return (chat.get("metadata") or {}).get("character") or ""

    def _chats_for_character(self, character, category=None):
        chats = [
            c for c in self.channel.context.chat.get_all()
            if self._chat_character(c) == character
        ]
        if category:
            chats = [c for c in chats if c.get("category") == category]
        return chats

    @webui.route("names")
    async def _route_names(self, body=None, query=None):
        """dropdown entries: stored key (what chats reference) + display name"""
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-23)
        # category added so the sidebar can filter its character dropdown
        entries = {
            key: {"name": char.get("name") or key, "category": char.get("category") or ""}
            for key, char in self.characters.items()
        }
        return sorted(
            ({"key": k, "name": v["name"], "category": v["category"]} for k, v in entries.items()),
            key=lambda e: e["name"].lower()
        )

    @webui.route("chats_count")
    async def _route_chats_count(self, body=None, query=None):
        """how many chats each character has, keyed by the stored character value"""
        counts = {}
        for chat in self.channel.context.chat.get_all():
            char = self._chat_character(chat)
            if char:
                counts[char] = counts.get(char, 0) + 1
        return counts

    @webui.route("apply", method="POST", admin_only=True)
    async def _route_apply(self, body=None, query=None):
        """sets (or clears, with an empty name) the character on the current
        chat without any switch side effects - meant for tagging freshly
        created chats from the sidebar"""
        name = str((body or {}).get("name", "")).strip()
        if not name:
            self.channel.context.chat.get("metadata")["character"] = ""
            return self.result("character cleared")

        char = self._find_character(name)
        if not char:
            return self.result("character not found", success=False)

        char_name = self._find_char_name(name) or char.get("name")
        self.channel.context.chat.get("metadata")["character"] = char_name
        return self.result(char_name)

    @webui.route("chats")
    async def _route_chats(self, body=None, query=None):
        """flat, updated-desc chat list for one character (the sidebar
        panel keeps its own simple list - no day-group machinery here).
        the old __none__ untagged-chats mode was dropped: the panel shows
        nothing until a character is picked."""
        character = (query or {}).get("character", "")
        chats = self._chats_for_character(character)
        return [
            {
                "id": c.get("id"),
                "title": c.get("title") or "New chat",
                "updated": c.get("updated") or "",
            }
            for c in chats
        ]

    @webui.route("create_chat", method="POST")
    async def _route_create_chat(self, body=None, query=None):
        """create a fresh chat already stamped with the character (passed
        straight into chat.new()'s metadata, so there's no window where
        the chat exists untagged). returns the new id; the panel then
        loads it via the core loadChat()."""
        name = str((body or {}).get("name", "")).strip()
        char = self._find_character(name)
        if not char:
            return self.result("character not found", success=False)

        char_key = self._find_char_name(name) or char.get("name")
        # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-04)
        # New chats go into the category configured in the module settings.
        chat_id = await self.channel.context.chat.new(
            category=self.config.get("category") or "general",
            title="New chat", metadata={"character": char_key}
        )
        return {"id": chat_id}
