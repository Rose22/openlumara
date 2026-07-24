import core
import json

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
        "use_writing_style": {
            "description": "Whether to use the writing style defined by the `writing style` module for characters. This will add that module's prompt to the character prompt even if agent prompts are disabled, making all your characters use your preferred writing style setup",
            "default": True
        }
    }

    # since we use a tool based approach, and char card v2's naming is confusing for an AI,
    # i've renamed the fields and just internally convert them to char card V1's names
    char_card_v1_mappings = {
        "name": "name",
        "description": "identity",
        "personality": "short_summary",
        "scenario": "scenario",
        "first_mes": "first_message",
        "mes_example": "example_conversation"
    }

    header = "Character"

    async def on_ready(self):
        self.characters = core.storage.StorageDict("characters", type="json")
        self.user_profile = core.storage.StorageDict("character_user", "json")
        self.active = False

        if self.config.get("insert_system_prompt"):
            # disable character listing tool
            self.disabled_tools.append("get_all")

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
            self.active = True
            if char:
                return f"currently active character: {char}"
            else:
                return "please provide a character name."
        elif name in("reset", "default"):
                self.channel.context.chat.get("metadata")["character"] = "character"
                self.active = False
                return "character has been reset to default"

        character = self._find_character(name)
        if not character:
            return f"character {name} does not exist!"

        response = await self.switch(character)

        return f"character switched to {character}"

    async def on_system_prompt(self):
        curr_char = await self.channel.context.chat.get("metadata").get("character")

        tool_text = f"Characters available to switch yourself to:\n{await self._list_characters()}" if (
            core.config.get("model", {}).get("use_tools") and
            self.config.get("insert_system_prompt") and
            not curr_char
        ) else ""

        if not curr_char:
            return tool_text or None

        char_name = await self.channel.context.chat.get("metadata").get("character")
        char = self.characters.get(char_name)

        # the presence of the "data" key means it's
        # either character card V2 or V3 or higher
        char_data = char.get("data")

        char_profile = None
        char_scenario = None
        first_msg = None
        if char_data:
            char_profile = char_data.get("description")
            char_scenario = char_data.get('scenario')
            first_msg = char_data.get("first_mes")
        else:
            # check if this is the legacy openlumara format or character spec V1,
            # otherwise don't use the character

            # if there is an "identity" key, this is openlumara's legacy format
            if "identity" in char.keys():
                char_profile = char.get("identity")

            # otherwise, if there is a "description" field, this is char spec V1
            elif "description" in char.keys():
                char_profile = char.get("description")
                char_scenario = char.get("scenario")
                first_msg = char.get("first_mes")

        if not char_profile:
            return "Failed to extract character profile from character JSON"

        # replace tags such as {{user}} and {{char}}
        char_profile = self._replace_tags(char_name, char_profile)
        if char_scenario:
            char_scenario = self._replace_tags(char_name, char_scenario)

        # all of this is stored as json strings, so newlines need to be restored
        char_profile = char_profile.replace("\\n", "\n")
        if char_scenario:
            char_scenario = char_scenario.replace("\\n", "\n")

        character_text_build = []
        character_text_build.append(f"## You: {char_name}\n{char_profile}")

        if char_data and char_scenario:
            character_text_build.append(f"## Scenario\n{char_scenario}")

        user_profile = self.user_profile.get("profile")
        if user_profile:
            user_name = self.user_profile.get("name")
            character_text_build.append(f"## The user: {user_name}")
            character_text_build.append(user_profile)

        char_text = "\n\n".join(character_text_build)

        # if this is an empty chat, insert the first message into history by sending it as a push
        if first_msg:
            if len(await self.channel.context.chat.messages.get()) == 0:
                first_msg = self._replace_tags(char_name, first_msg)
                await self.channel.push({"role": "assistant", "content": first_msg})
                await self.channel.context.chat.messages.add({"role": "assistant", "content": first_msg})

        return char_text

    async def on_end_prompt(self):
        curr_char = await self.channel.context.chat.get("metadata").get("character")
        if not curr_char:
            return None

        char = self._find_character(curr_char)
        if not char:
            return None

        char_data = char.get("data")
        if not char_data:
            return None

        return char_data.get("post_history_instructions")

    async def switch(self, name: str):
        """Switches you to a different character. This will change your personality! Use this if user requests it."""
        char = self._find_character(name)
        if not char:
            return self.result("character not found", False)

        char_data = char.get("data", {})
        if not char_data:
            # default back to legacy openlumara character format
            char_identity = char.get("identity")
            if not char_identity:
                return self.result("character data not found and auto conversion of legacy character format failed", False)

            char_data = {
                "name": name,
                "description": char.get("identity")
            }

        self.channel.context.chat.get("metadata")["character"] = char_data.get("name")
        self.active = True
        user_name = self.user_profile.get("name", "User")

        first_msg = char_data.get("first_mes")
        if first_msg:
            # bypass the usual tool response flow and instead send the first message as a push message
            first_msg = self._replace_tags(name, first_msg)
            await self.channel.push({"role": "assistant", "content": first_msg})
            await self.channel.context.chat.messages.add({"role": "assistant", "content": first_msg})
            return None

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

    async def add(self, name: str, profile: str, short_summary: str, scenario: str, category: str, tags: list = [], first_message: str = "", post_history_instructions: str = ""):
        """
        Adds a new character to your character storage.

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            short_summary: A short summary of the character
            scenario: The scenario/scene in which the conversation will take place
            tags: Any tags that could be used to organize the character profile
            first_message: The first message the character will send when starting a new chat. Optional.
            post_history_instructions: Prompt to append at the end of chat history. Optional.
        """
        if not name.strip():
            return self.result("character name cannot be empty", False)

        exists = self._find_character(name)
        if exists:
            return self.result("character already exists", False)

        if not profile:
            return self.result("character profile must not be blank.")

        self.characters[name] = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "category": category,
            "data": {
                "name": name,
                "description": profile,
                "personality": short_summary,
                "scenario": scenario,
                "first_mes": first_message,
                "mes_example": "", # why
                "tags": tags,

                "creator_notes": "", # not needed for openlumara
                "system_prompt": "", # not needed for openlumara
                "post_history_instructions": post_history_instructions,
                "alternate_greetings": [], # no
                "creator": self.user_profile.get("name", "OpenLumara User"),
                "character_version": "1.0",
                "extensions": {}
            }
        }
        self.characters.save()
        return self.result("character added")

    async def edit(self, name: str, profile: str = None, short_summary: str = None, scenario: str = None, category: str = None, tags: list = None, first_message: str = None, post_history_instructions: str = None):
        """
        Edits an existing character. All fields except name are optional.

        Args:
            name: The character's name
            profile: The main description of the character. Within it, use {{char}} to refer to the character and {{user}} to refer to the user.
            short_summary: A short summary of the character
            scenario: The scenario/scene in which the conversation will take place
            tags: Any tags that could be used to organize the character profile
            first_message: The first message the character will send when starting a new chat.
            post_history_instructions: Prompt to append at the end of chat history.
        """
        if not name.strip():
            return self.result("character name cannot be empty", False)

        char = self._find_character(name)
        if not char:
            return self.result("character doesn't exist!", False)

        char_data = char.get("data")
        if not char_data:
            return self.result("character data doesn't exist!", False)

        ver_increment = float(char.get("character_version", 1.0))+0.1

        # we're using `is not None` because we need to retain the ability
        # to set stuff to blank strings
        self.characters[name] = {
            "spec": "chara_card_v2",
            "spec_version": "2.0",
            "category": category,
            "data": {
                "name": name,
                "description": profile if profile is not None else char_data.get("description"),
                "personality": short_summary if short_summary is not None else char_data.get("personality"),
                "scenario": scenario if scenario is not None else char_data.get("scenario"),
                "first_mes": first_message if first_message is not None else char_data.get("first_mes"),
                "mes_example": "", # why
                "tags": tags if tags is not None else char_data.get("tags"),
                "creator_notes": "", # not needed for openlumara
                "system_prompt": "", # not needed for openlumara
                "post_history_instructions": post_history_instructions if post_history_instructions is not None else char_data.get("post_history_instructions"),
                "alternate_greetings": [], # no
                "creator": char_data.get("creator") or self.user_profile.get("name", "OpenLumara User"),
                "character_version": ver_increment,
                "extensions": {}
            }
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
        name = self._find_character(name)
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

    async def import_json(self, json_code: str):
        """imports a json character V2 card into your character storage"""
        try:
            char_obj = json.loads(json_code)
        except Exception as e:
            return self.result(f"error: {core.detail_error(e)}", success=False)

        if not char_obj:
            return self.result("error: character card was empty", success=False)

        char_data = char_obj.get("data")
        if not char_data:
            # might be char card V1, try to get the name first
            if not char_obj.get("name"):
                return self.result("error: character card did not have a data field", success=False)

            # if so, convert it to V2
            char_obj = {
                "spec": "chara_card_v2",
                "spec_version": "2.0",
                "data": char_obj
            }

        char_name = char_data.get("name")

        if not char_name:
            return self.result("error: failed to extract character name from character data", success=False)

        # add it to storage
        self.characters[char_name] = char_obj
        self.characters.save()

        return self.result("character successfully imported")

    @core.module.command("username")
    async def cmd_set_user_name(self, args: list):
        name = " ".join(args)
        self.user_profile["name"] = name
        self.user_profile.save()
        return "Your name has been set!"
