import core

class Characters(core.module.Module):
    """Lets your AI embody different characters! inspired by characterAI, janitorAI, sillytavern, etc."""

    settings = {
        "put_character_list_in_system_prompt": True,
        "disable_agent_prompts_when_character_active": True
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.characters = core.storage.StorageDict("characters", type="json")
        self.user_profile = core.storage.StorageDict("character_user", "json")
        self.active = False

        self._header = "Identity"

        if self.config.get("put_character_list_in_system_prompt"):
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
            char = await self.channel.context.chat.get_data("character")
            self.active = True
            if char:
                return f"currently active character: {char}"
            else:
                return "please provide a character name."
        elif name in("reset", "default"):
                await self.channel.context.chat.set_data("character", "")
                self.active = False
                return "character has been reset to default"

        character = self._find_character(name)
        if not character:
            return f"character {name} does not exist!"
        response = await self.switch(character)
        return f"character switched to {character}"

    async def on_system_prompt(self):
        curr_char = await self.channel.context.chat.get_data("character")

        tool_text = f"Characters available to switch yourself to:\n{await self._list_characters()}" if (
            core.config.get("model", {}).get("use_tools") and
            self.config.get("put_character_list_in_system_prompt") and
            not curr_char
        ) else ""

        if not curr_char:
            return tool_text or None

        char_name = await self.channel.context.chat.get_data("character")
        char_profile = self._rewrite_character(char_name, self.characters.get(char_name, {}).get("identity", ""))
        user_name = self.user_profile.get("name", "User")
        user_prefs = self.user_profile.get("preferences", "")

        # all of this is stored as json strings, so newlines need to be restored
        char_profile = char_profile.replace("\\n", "\n")
        user_prefs = user_prefs.replace("\\n", "\n")

        char_text = f"You are {char_name}. You are talking to {user_name}.\n\n{char_profile}\n\n{user_prefs}\n{tool_text}"

        return char_text

    async def switch(self, name: str):
        """Switches you to a different character. This will change your personality! Use this if user requests it."""
        name = self._find_character(name)
        if not name:
            return self.result("character not found", False)
        character = self.characters.get(name)
        await self.channel.context.chat.set_data("character", name)

        self.active = True

        user_name = self.user_profile.get("name", "User")
        preferences = self.user_profile.get("preferences", "")
        return self.result(f"Switch successful. Write your response as the character's first message.")
    
    async def switch_to_default(self):
        """Switches you back to your default identity."""
        await self.channel.context.chat.set_data("character", "")
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

        for character_name in self.characters.keys():
            if character_name.lower().strip() == name.lower().strip():
                return character_name
        return None

    def _rewrite_character(self, name: str, character: str):
        """rewrites a character to automatically port over character cards"""
        user_name = self.user_profile.get("name", "user")
        replacement_map = {
            "{{char}}": name,
            "{char}": name,
            "{{user}}": user_name,
            "{user}": user_name,
            "you": name,
            "user": user_name
        }

        for word, replacement in replacement_map.items():
            character = self._case_insensitive_replace(character, word, replacement)

        return character

    async def add(self, name: str, character: str, category: str):
        """Adds a new character to your character storage. Defines who you are as an AI. Also defines your writing style. Use `{char}` to refer to yourself. Use `{user}` to refer to the user."""
        if not name.strip():
            return self.result("character name cannot be empty", False)

        exists = self._find_character(name)
        if exists:
            return self.result("character already exists", False)

        if not character:
            return self.result("character must not be blank.")

        self.characters[name] = {
            "identity": character,
            "category": category.lower()
        }
        self.characters.save()
        return self.result("character added")

    async def read(self, name: str):
        """
        Reads a character profile.
        DO NOT use if trying to read the character you're currently switched to!
        ALWAYS use before editing a character!
        """
        char_name = self._find_character(name)
        if not char_name:
            return "character does not exist!"

        character = self.characters[char_name]
        character_profile = character.get("identity", "")
        character_profile = character_profile.replace("\\n", "\n")

        return self.result(character_profile)

    async def edit(self, name: str, category: str, character: str):
        """Edits an existing character. Use ONLY if user explicitly requests it. When using this tool, write out the full character definition. This tool fully replaces the definition! Don't summarize a character definition. Write out the FULL profile. Use {char} to refer to yourself. Use {user} to refer to the user."""
        name = self._find_character(name)
        if not name:
            return self.result("character doesn't exist!", False)

        if not None and len(character) > 0:
            self.characters[name]["identity"] = character
        if category:
            self.characters[name]["category"] = category.lower()

        self.characters.save()
        return self.result("character edited.")

    async def delete(self, name: str):
        """Deletes a character. Use ONLY if user explicitly requests it."""
        name = self._find_character(name)
        if name in self.characters.keys():
            self.characters.pop(name, None)
            self.characters.save()
            return self.result(f"character {name} deleted")
        return self.result("character doesn't exist!", False)

    async def set_user_name(self, name: str):
        self.user_profile["name"] = name
        self.user_profile.save()
        return self.result("name set")

    @core.module.command("username")
    async def cmd_set_user_name(self, args: list):
        name = " ".join(args)
        self.user_profile["preferences"] = preferences
        self.user_profile.save()
        return "Your name has been set!"

    async def set_preferences(self, preferences: str):
        """Sets any preferences the user has for the writing style and tone of the characters. e.g. "Write your replies in a short, easy to understand style, in at most 2 paragraphs."""
        self.user_profile["preferences"] = preferences
        self.user_profile.save()
        return self.result("preferences set")

    # command version
    @core.module.command("charpref")
    async def cmd_set_preferences(self, args: list):
        """sets your preferred writing style for characters"""
        if not args:
            return self.user_profile.get("preferences", "no preferences have been configured yet")

        pref = " ".join(args)
        self.user_profile["preferences"] = pref
        self.user_profile.save()
        return "preferences set!"

    # async def list(self):
    #     """
    #     Returns a list of all your characters.
    #     """
    #     return self.result(self.characters)
