import core
import json
import os
import shutil
import sys
import channels.webui.api as webui

# -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
# Full rewrite: characters live in one flat internal format (name + profile + optional scenario/first_message/post_history/category/tags),
# stored as a folder of json files. Character card specs (V1/V2) are only understood at the import boundary.

class Characters(core.module.Module):
    """Lets your AI embody different characters! inspired by characterAI, janitorAI, sillytavern, etc."""

    settings = {
        "insert_system_prompt": {
            "default": True,
            "description": "Put the list of stored characters into the system prompt so that the AI always knows what characters it can switch to"
        },
        "disable_agent_prompts_when_character_active": {
            "default": True,
            "description": "Automatically disables all prompts from other modules when a character is active, so that the only thing in the system prompt is the character definition. This can help a lot with making characters behave purely like characters, and less like, well, personal assistants."
        },
        "use_first_messages": {
            "description": "Whether a character's first message gets sent automatically when switching to that character in an empty chat",
            "default": True
        },
        "use_post_history_instructions": {
            "description": "Whether a character's post-history instructions (usually imported from character cards) get appended to the end of the prompt",
            "default": True
        },
        "use_writing_style": {
            "description": "Whether to use the writing style defined by the `writing style` module for characters. This will add that module's prompt to the character prompt even if agent prompts are disabled, making all your characters use your preferred writing style setup",
            "default": True
        }
    }

    header = "Character"

    async def on_ready(self):
        self.characters = core.storage.StorageDict("characters", type="json_folder")
        self.user_profile = core.storage.StorageDict("character_user", "json")
        self.active = False

        self._migrate_if_needed()
        self._ingest_pngs()
        self._normalize_all()

        if self.config.get("insert_system_prompt"):
            # disable character listing tool
            self.disabled_tools.append("get_all")

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

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
    # Converts any supported card format (internal / legacy openlumara / char card V1 / V2) into the flat internal format.
    def _normalize_character(self, stored_key, char):
        """converts a character of any supported format into openlumara's flat internal format"""
        if not isinstance(char, dict):
            return None

        if "profile" in char:
            # already internal format; just make sure every field exists
            return {
                "name": char.get("name") or stored_key,
                "profile": char.get("profile", ""),
                "scenario": char.get("scenario", ""),
                "first_message": char.get("first_message", ""),
                "post_history": char.get("post_history", ""),
                "category": char.get("category"),
                "tags": char.get("tags", [])
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
        if extras:
            profile = profile + "\n\n" + "\n\n".join(extras)

        return {
            "name": name,
            "profile": profile,
            "scenario": card.get("scenario", ""),
            "first_message": card.get("first_mes", char.get("first_message", "")),
            "post_history": card.get("post_history_instructions", ""),
            "category": char.get("category"),
            "tags": card.get("tags", char.get("tags", []))
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
            with open(png_path, "rb") as f:
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
        for filename in os.listdir(folder):
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
                self.active = False
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

        tool_text = f"Characters available to switch yourself to:\n{await self._list_characters()}" if (
            core.config.get("model", {}).get("use_tools") and
            self.config.get("insert_system_prompt") and
            not curr_char
        ) else ""

        if not curr_char:
            return tool_text or None

        char = self._find_character(curr_char)

        # if the character was deleted (or the metadata holds a stale/invalid
        # value), clean it up so the rest of the prompt isn't broken
        if not char:
            self.channel.context.chat.get("metadata")["character"] = ""
            self.active = False
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

        user_profile = self.user_profile.get("profile")
        if user_profile:
            user_name = self.user_profile.get("name")
            character_text_build.append(f"## The user: {user_name}")
            character_text_build.append(user_profile)

        char_text = "\n\n".join(character_text_build)

        # if this is an empty chat, insert the first message into history by sending it as a push
        first_msg = char.get("first_message", "")
        if self.config.get("use_first_messages") and first_msg:
            if len(await self.channel.context.chat.messages.get()) == 0:
                first_msg = self._replace_tags(char_name, first_msg)
                await self.channel.push({"role": "assistant", "content": first_msg})

        return char_text

    async def on_end_prompt(self):
        if not self.config.get("use_post_history_instructions"):
            return None

        curr_char = self.channel.context.chat.get("metadata").get("character")
        if not curr_char:
            return None

        char = self._find_character(curr_char)
        if not char:
            return None

        return char.get("post_history") or None

    async def switch(self, name: str):
        """Switches you to a different character. This will change your personality! Use this if user requests it."""
        char = self._find_character(name)
        if not char:
            return self.result("character not found", False)

        # prefer the canonical stored key so on_system_prompt() can always
        # resolve the character reliably, regardless of how it was invoked
        char_name = self._find_char_name(name) or char.get("name")

        self.channel.context.chat.get("metadata")["character"] = char_name
        self.active = True

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

    async def switch_to_default(self):
        """Switches you back to your default identity."""
        self.channel.context.chat.get("metadata")["character"] = ""

        self.active = False
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
        user_name = self.user_profile.get("name", "user")
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

    async def add(self, name: str, profile: str, scenario: str = "", category: str = "", tags: list = None):
        """
        Adds a new character to your character storage.

        Note: new characters are created without a first message. If the user
        wants one, they can add it later with edit().

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            scenario: The scenario/scene in which the conversation will take place. Optional.
            category: Category to organize the character under. Optional.
            tags: Any tags that could be used to organize the character profile. Optional.
        """
        if not name.strip():
            return self.result("character name cannot be empty", False)

        if tags is None:
            tags = []

        exists = self._find_character(name)
        if exists:
            return self.result("character already exists", False)

        if not profile:
            return self.result("character profile must not be blank.")

        self.characters[name] = {
            "name": name,
            "profile": profile,
            "scenario": scenario,
            "first_message": "",
            "post_history": "",
            "category": category or None,
            "tags": tags
        }
        self.characters.save()
        return self.result("character added")

    async def edit(self, name: str, profile: str = None, scenario: str = None, category: str = None, tags: list = None, first_message: str = None, post_history: str = None):
        """
        Edits an existing character. All fields except name are optional.

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            scenario: The scenario/scene in which the conversation will take place
            category: Category to organize the character under
            tags: Any tags that could be used to organize the character profile
            first_message: The first message the character will send when starting a new chat.
            post_history: Prompt to append at the end of chat history.
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
            "profile": profile if profile is not None else char.get("profile", ""),
            "scenario": scenario if scenario is not None else char.get("scenario", ""),
            "first_message": first_message if first_message is not None else char.get("first_message", ""),
            "post_history": post_history if post_history is not None else char.get("post_history", ""),
            "category": category if category is not None else char.get("category"),
            "tags": tags if tags is not None else char.get("tags", [])
        }
        self.characters.save()
        return self.result("character edited")

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

    async def delete(self, name: str):
        """Deletes a character. Use ONLY if user explicitly requests it."""
        name = self._find_char_name(name)

        if name in self.characters.keys():
            self.characters.pop(name, None)
            self.characters.save()
            return self.result(f"character {name} deleted")

        return self.result("character doesn't exist!", False)

    async def set_user_persona(self, name: str, profile: str):
        self.user_profile["name"] = name
        self.user_profile["profile"] = profile
        self.user_profile.save()

        return self.result("user persona set")

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next-Q4) :: (2026-10-03)
    # Import is now the only place that understands the character card spec; cards are flattened into the internal format on the way in.
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

    @core.module.command("username")
    async def cmd_set_user_name(self, args: list):
        name = " ".join(args)
        self.user_profile["name"] = name
        self.user_profile.save()
        return "Your name has been set!"

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

    @webui.route("delete", method="POST")
    async def _route_delete(self, body=None, query=None):
        name = (body or {}).get("name", "")
        char = self._find_character(name)
        if not char:
            return self.result("character not found", success=False)
        stored_key = self._find_char_name(name)
        del self.characters[stored_key]
        self.characters.save()
        return self.result(f"deleted character {stored_key}")

    @webui.route("import", method="POST")
    async def _route_import(self, body=None, query=None):
        json_code = (body or {}).get("json_code", "")
        if isinstance(json_code, (dict, list)):
            json_code = json.dumps(json_code)
        return await self.import_json(json_code)
