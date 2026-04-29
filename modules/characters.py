import core

class Characters(core.module.Module):
    """Lets your AI embody different characters! inspired by characterAI, janitorAI, sillytavern, etc."""

    settings = {
        "disable_agent_prompts_when_character_active": True,
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.characters = core.storage.StorageDict("characters", type="json")
        self.user_profile = core.storage.StorageDict("character_user", "json")
        self._header = "Profiles"

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

    @core.module.command("character", help={
        "": "show current character",
        "<name>": "switch to character <name>",
        "reset": "switch to default AI assistant character"
    })
    async def cmd_switch(self, args: list):
        name = " ".join(args)
        if not name:
            char = await self.channel.context.chat.get_data("character")
            if char:
                return f"currently active character: {char}"
            else:
                return "please provide a character name."
        elif name in("reset", "default"):
                await self.channel.context.chat.set_data("character", "")
                return "character has been reset to default"

        character = self._find_character(name)
        if not character:
            return f"character {name} does not exist!"
        response = await self.switch(character)
        return f"character switched to {character}"

    async def on_system_prompt(self):
        curr_char = self.characters.get(await self.channel.context.chat.get_data("character"))
        tool_text = f"You can switch between identities using character_switch(). User can switch characters using the `/character` command. Characters available to switch yourself to:\n{await self._list_characters()}" if core.config.get("model", {}).get("use_tools") and not curr_char else ""
        if not curr_char: return tool_text
        char_name = await self.channel.context.chat.get_data("character")
        char_profile = self.characters.get(char_name, {}).get("identity", "")
        user_name = self.user_profile.get("name", "User")
        prefs = self.user_profile.get("preferences", "")
        char_text = f"Name: {char_name}\nProfile: {char_profile}\n\nWrite your replies as {char_name} in a chat between {char_name} and {user_name}. {prefs}"
        user_prof = f"## User\nName: {self.user_profile.get('name')}\nProfile: {self.user_profile.get('profile')}" if self.user_profile else ""
        return f"{user_prof}\n\n## You\n{char_text}\n\n{tool_text}"

    async def switch(self, name: str):
        """Switches you to a different character. This will change your personality! Use this if user requests it."""
        name = self._find_character(name)
        if not name:
            return self.result("character not found", False)
        character = self.characters.get(name)
        await self.channel.context.chat.set_data("character", name)

        user_name = self.user_profile.get("name", "User")
        preferences = self.user_profile.get("preferences", "")
        return self.result(str({"instructions": f"Write your next reply as {name} in a chat between {name} and {user_name}. {preferences}", "character": self._rewrite_character(name, character.get("identity"))}))
    
    async def switch_to_default(self):
        """Switches you back to your default identity."""
        await self.channel.context.chat.set_data("character", "")
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
            "you are": f"{name} is",
            "you should": f"{name} should",
            "you must": f"{name} must",
            "you want": f"{name} wants",
            "you have": f"{name} has"
        }

        for word, replacement in replacement_map.items():
            character = self._case_insensitive_replace(character, word, replacement)

        return character

    async def add(self, name: str, character: str, category: str):
        """Adds a new character to your character storage. Defines who you are as an AI. Also defines your writing style. Use {char} to refer to yourself. Use {user} to refer to the user."""
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

    # async def read(self, name: str):
    #     """
    #     Reads a character profile.
    #     DO NOT use if trying to read the character you're currently switched to!
    #     ALWAYS use before editing a character!
    #     """
    #     char_name = self._find_character(name)
    #     if not char_name:
    #         return "character does not exist!"
    #
    #     character = self.characters[char_name]
    #     character_profile = character.get("identity", "")
    #
    #     return self.result(character_profile)

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

    async def set_user_profile(self, name: str, profile: str):
        self.user_profile["name"] = name
        self.user_profile["profile"] = profile
        self.user_profile.save()
        return self.result("profile set")
    async def clear_user_profile(self):
        """Clears the profile of the user. ONLY use if user explicitly asks for it!"""
        del(self.user_profile["name"])
        del(self.user_profile["profile"])
        self.user_profile.save()
        return self.result("profile cleared")

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
