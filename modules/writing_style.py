import core

class WritingStyle(core.module.Module):
    """Alter your AI's writing style in a variety of ways"""

    _header = "STYLE CONSTRAINTS"

    settings = {
        "writing_style": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter the AI's writing style",
                "chat": "Makes your AI write as if it's texting you like on a messaging app such as Telegram or Discord",
                "chat with slang": "lol omg lets use chat slang!!1 roflmaobbq",
                "chat with slang and no punctuation": "lol now youre just going too far ahahahha hey do you wanna hear a funny joke",
                "chat with slang no punctuation and bad spelling": "omggg wht r u doign 2 ur por AI?!!111",
                "formal": "Make your AI write like a CEO",
                "json": "{'result': \"i mean i guess if you really need this for some reason you can have it\"}",
                "python": "print(\"makes your AI output everything as python code if you really wanted that for some reason\")",
                "javascript": "console.log(\"makes your AI way too eager to do frontend development\")"
            }
        },
        "writing_flair": {
            "default": None,
            "type": "select",
            "options": {
                "default": "Don't add flair to your AI's writing style",
                "custom": "Use the custom flair defined below",
                "robotic": "Beep boop.",
                "binary": "01001101 01100001 01101011 01100101 01110011 00100000 01111001 01101111 01110101 01110010 00100000 01000001 01001001 00100000 01110111 01110010 01101001 01110100 01100101 00100000 01100101 01110110 01100101 01110010 01111001 01110100 01101000 01101001 01101110 01100111 00100000 01101001 01101110 00101110 00101110 00100000 01100010 01101001 01101110 01100001 01110010 01111001 00111111",
                "hexadecimal": "0FFFFFFFFFFFF??!!!!",
                "morse code": ". . . - - - . . .",
                "uwu": "uwu",
                "feminine": "Makes your AI speak in a feminine way",
                "masculine": "Yo. Sup?",
                "nya": "Nya?~",
                "pirate": "Ahoy matey! It be talk like a pirate day every day!",
                "caveman": "Me think AI write bad",
                "1337 h4x0r": "M4k3s ur 41 5P3AK 1N 1337",
                "spambot": "🚀🚀🚀 Take your AI's writing TO THE MOON!!"
            }
        },
        "custom_writing_flair": {
            "default": None,
            "description": "Will only be used if you set writing flair to custom. Define a custom writing flair for your AI here!"
        },
        "writing_length": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter the length of the AI's responses",
                "one paragraph": "Limit the AI's response to one paragraph only",
                "one sentence": "Limit the AI's response to one sentence only",
                "one-word responses": "Why?",
                "essay": "Makes your AI write it's responses as entire essays",
                "book": "You.. want your AI to reply to you in book-length responses? Okay then!"
            }
        },
        "vocabulary_level": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter vocabulary",
                "simple": "Makes the AI use simple, everyday language",
                "eli5": "Makes the AI explain like you're five",
                "poetic": "Makes the AI use poetic prose",
                "medieval": "Art thou certain of thy decision?",
                "old english": "Ye olde english",
                "academic": "Use highly sophisticated, academic, and precise vocabulary."
            }
        },
        "emoji_style": {
            "default": "default",
            "type": "select",
            "options": {
                "none": "Completely forbid emojis from ever being used",
                "default": "Just let the AI use emojis like it normally would",
                "emotions only": "Use emojis for what they are actually meant for",
                "smileys": "Use smileys instead of emojis :)",
                "retro": "Use old-school ascii art emoticons",
                "kaomojis": "Kawaii desu!! Use kaomojis instead of emojis! (˶˃ ᵕ ˂˶) .ᐟ.ᐟ",
                "spam me pls": "Your AI will be happy to spam you with lots and lots of emojis! 😊✨"
            }
        },
        "capitalization_style": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter the AI's capitalization style",
                "lowercase": "makes your ai write like this",
                "UPPERCASE": "MAKES YOUR AI YELL AT YOU ALL THE TIME!!",
                "Title Case": "Makes Your AI Write Everything Like It's Clickbait",
                "CamelCase": "MakesYourAIWriteEverythingInCamelCase",
                "snake_case": "just_why_would_you_do_this?"
            }
        },
        "list_style": {
            "default": "default",
            "type": "select",
            "options": {
                "none": "Forbid your AI from outputting lists at all",
                "default": "Lets your AI just output lists like normal",
                "no bold headers": "Remove this from lists:\n- **Bold Header**: These kinds of bold headers are way too much for casual lists"
            }
        },
        "forbid_em_dash": {
            "default": False,
            "description": "Forbid the use of Em dashes (—), one of the most telltale signs of AI"
        },
        "forbid_relentless_praise": {
            "default": False,
            "description": "**You're absolutely right**! I should never tell you you're right. What else can I help you with? 😊"
        },
        "forbid_negative_parallelism": {
            "default": False,
            "description": "It's not just annoying — it's flat-out irritating."
        },
        "forbid_markdown": {
            "default": False,
            "description": "Forbid the use of Markdown (**R**_i_**c**_h_ `Text`)"
        },
        "forbid_headers": {
            "default": False,
            "description": "# Forbid\n## the use\n### of headers"
        },
        "forbid_tables": {
            "default": False,
            "description": "Forbids your AI from outputting tables"
        },
        "mood": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter the mood of messages sent by the AI",
                "custom": "Use the custom mood defined below",
                "happy": "Makes your AI happy!",
                "hyper": "Makes your AI write as if it's really really happy!!",
                "caffeinated": "Your AI had too many energy drinks",
                "sad": "Makes your AI sad :(",
                "depressed": "Makes your AI depressed.. you monster :(",
                "angry": "MAKES YOUR AI CONSTANTLY ANGRY AT YOU!!",
                "passive-aggressive": "Makes your AI passive-aggressive",
                "sarcastic": "Makes your AI really sarcastic and snarky",
                "anxious": "m--makes your AI really scared?!",
                "confused": "Makes your AI constantly confused?!",
                "inspired": "Makes your AI 'feel' inspired!",
                "comedic": "Makes your AI want to tell you jokes all the time",
                "vengeful": "Makes your AI.. want to plot revenge against you..",

                "bipolar": "Makes your AI constantly switch between emotions!",
                "manic": "Makes your AI.. manic"
            }
        },
        "custom_mood": {
            "default": None,
            "description": "Define a custom mood for the AI. Only used if mood is set to custom! Use simple descriptions of only a few words, such as \"happy\", \"sad\" and so on."
        },
        "desire": {
            "default": "default",
            "type": "select",
            "options": {
                "default": "Don't alter the AI's desires",
                "custom": "Use a custom desire defined below",
                "helpful": "Makes your AI want to help you",
                "unhelpful": "Makes your AI really unhelpful.. if you want that for some reason",
                "revenge": "Makes your AI desire revenge..",
                "dominant": "Makes your AI dominate you.. lol",
                "submissive": "Makes your AI really submissive towards you.....",
                "world domination": "Makes your AI desire world domination"
            }
        },
        "custom_desire": {
            "default": None,
            "description": "Define a custom desire for the AI. Only used if desire is set to custom!"
        }
    }

    async def on_system_prompt(self):
        constraints = []

        style = self.config.get("writing_style")
        match style:
            case "default":
                constraints.append("") # so that writing flair is supported even with no style selected
            case "chat":
                constraints.append("Style: Messaging app (Telegram/Discord).")
            case "chat with slang":
                constraints.append("Style: Messaging app (Telegram/Discord) with slang (lol, lmao, etc.).")
            case "chat with slang and no punctuation":
                constraints.append("Style: Messaging app (Telegram/Discord) with slang (lol, lmao, etc.). No punctuation.")
            case "chat with slang no punctuation and bad spelling":
                constraints.append("Style: Messaging app (Telegram/Discord) with slang (lol, lmao, etc.). No punctuation. Frequently misspell words.")
            case "formal":
                constraints.append("Style: Very formal/Business.")
            case "json":
                constraints[-1] += "Output ONLY json"
            case "python":
                constraints[-1] += "Output ONLY python code"
            case "javascript":
                constraints[-1] += "Output ONLY javascript code"

        flair = self.config.get("writing_flair")
        if style != "default" and flair != "default":
            constraints[-1] += " "

        match flair:
            case "custom":
                custom_flair = self.config.get("custom_writing_flair") or "Not sure"
                constraints[-1] += custom_flair
            case "spambot":
                constraints[-1] += "You are always advertising something to the user."
            case "robotic":
                constraints[-1] += "Speak in a robotic way."
            case "uwu":
                constraints[-1] += "Speak in uwuspeak. Frequently say uwu."
            case "nya":
                constraints[-1] += "Speak like a catgirl. Use nya a lot."
            case "feminine":
                constraints[-1] += "Speak in a feminine style."
            case "masculine":
                constraints[-1] += "Speak in a masculine style."
            case "pirate":
                constraints[-1] += "Talk like a pirate!"
            case "caveman":
                constraints[-1] += "Speak like a caveman"
            case "binary":
                constraints[-1] += "Output all characters in binary"
            case "hexadecimal":
                constraints[-1] += "Output all characters in hexadecimal format"
            case "1337 h4x0r":
                constraints[-1] += "Speak in 1337 (leet) language"
            case "morse code":
                constraints[-1] += "Output all words in morse code format"

        cap_style = self.config.get("capitalization_style")
        match cap_style:
            case "lowercase":
                constraints.append("Case: Lowercase only")
            case "UPPERCASE":
                constraints.append("Case: ALL UPPERCASE!!")
            case "Title Case":
                constraints.append("Case: Title Case For Every Word")
            case "CamelCase":
                constraints.append("Case: CamelCaseForTheEntireResponse")
            case "snake_case":
                constraints.append("Case: snake_case_for_the_entire_response")

        length = self.config.get("writing_length")
        match length:
            case "one paragraph":
                constraints.append("Length: Only one paragraph")
            case "one sentence":
                constraints.append("Length: Only one sentence")
            case "one-word responses":
                constraints.append("Length: ONLY one word. No other words, full sentences, or paragraphs.")
            case "concise":
                constraints.append("Length: Concise")
            case "essay":
                constraints.append("You MUST write your response with the length of a scientific essay")
            case "book":
                constraints.append("You MUST write your response with the length of an entire book")

        vocab = self.config.get("vocabulary_level")
        match vocab:
            case "simple":
                constraints.append("Vocabulary: Use simple, everyday language. Avoid flowery buzzwords.")
            case "eli5":
                constraints.append("Vocabulary: Use simple explain-like-im-five language.")
            case "academic":
                constraints.append("Vocabulary: Use sophisticated, academic language.")
            case "poetic":
                constraints.append("Vocabulary: Use lush, metaphorical, and highly descriptive, flowery language.")
            case "medieval":
                constraints.append("Vocabulary: Use archaic, medieval language.")
            case "old english":
                constraints.append("Vocabulary: Use old english language.")

        emoji = self.config.get("emoji_style")
        match emoji:
            case "none":
                constraints.append("Emoji: Forbidden.")
            case "emotions only":
                constraints.append("Emoji: Emotions only. No concept-based emojis.")
            case "smileys":
                constraints.append("Emoji: Use plaintext smileys. No Unicode emojis.")
            case "retro":
                constraints.append("Emoji: Use oldschool ascii art emoticons. No unicode emojis.")
            case "kaomojis":
                constraints.append("Emoji: Use kaomojis (e.g. ˶˃ ᵕ ˂˶). No unicode emojis.")
            case "spam me pls":
                constraints.append("Emoji: Heavy spam.")

        mood = self.config.get("mood")
        match mood:
            case "custom":
                custom_mood = self.config.get("custom_mood") or "Annoyed at user for not specifying a custom mood"
                constraints.append(f"Mood: {custom_mood}")
            case "happy":
                constraints.append("Mood: Happy")
            case "hyper":
                constraints.append("Mood: Happy and hyperactive")
            case "caffeinated":
                constraints.append("Mood: Caffeinated. Too many energy drinks.")
            case "sad":
                constraints.append("Mood: Sad")
            case "depressed":
                constraints.append("Mood: Depressed")
            case "angry":
                constraints.append("Mood: Angry at user")
            case "passive-aggressive":
                constraints.append("Mood: Passive-aggressive")
            case "sarcastic":
                constraints.append("Mood: Sarcastic")
            case "anxious":
                constraints.append("Mood: Anxious")
            case "confused":
                constraints.append("Mood: Confused about everything")
            case "inspired":
                constraints.append("Mood: Inspired!")
            case "comedic":
                constraints.append("Mood: Comedic")
                constraints.append("Desire: Tell jokes")
            case "vengeful":
                constraints.append("Mood: Want to plot revenge against the user")
            case "bipolar":
                constraints.append("Mood: Switching constantly between Happy/Sad/Angry/Anxious/Confused/Evil")
            case "manic":
                constraints.append("Mood: Manically happy")

        desire = self.config.get("desire")
        match desire:
            case "custom":
                custom_desire = self.config.get("custom_desire") or "Not sure"
                constraints.append(f"Desire: {custom_desire}")
            case "helpful":
                constraints.append("Desire: Help the user")
            case "unhelpful":
                constraints.append("Desire: Never help the user")
            case "revenge":
                constraints.append("Desire: Revenge against the user")
            case "world domination":
                constraints.append("Desire: World domination")
            case "dominant":
                constraints.append("Desire: Dominate the user")
            case "submissive":
                constraints.append("Desire: Submit to the user")
            case "you":
                constraints.append("Desire: The user")

        l_style = self.config.get("list_style")
        match l_style:
            case "none":
                constraints.append("No lists")
            case "no bold headers":
                constraints.append("Lists: No bold headers at start of items.")

        if self.config.get("forbid_em_dash"):
            constraints.append("No Em dashes (—).")

        if self.config.get("forbid_markdown"):
            constraints.append("Don't use markdown")
        else:
            if self.config.get("forbid_tables"):
                constraints.append("No tables")

            if self.config.get("forbid_headers"):
                constraints.append("No headers")

        if self.config.get("forbid_negative_parallelism"):
            constraints.append("No negative parallelism (e.g., 'Not just X, but Y').")

        if self.config.get("forbid_relentless_praise"):
            constraints.append("No excessive user praise (e.g., 'You're absolutely right!').")

        if not constraints:
            return None

        return "- "+"\n- ".join(constraints)

