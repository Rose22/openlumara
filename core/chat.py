import core
import ulid
import datetime
import os

class Chat:
    DEFAULT_DATA = {
        "title": "",
        "category": "general",
        "tags": [],
        "custom_data": {},
    }

    """contains openAI messages array, and can save and load sets of messages from files"""
    def __init__(self, channel):
        self.data = core.storage.StorageList(f"{channel.name}_chats", "json")
        self.channel = channel
        self.current = None
        self.current_save_path = os.path.join(core.get_data_path(), f"{self.channel.name}_current_chat")
        self.token_usage = 0 # uses API results to cache last message's token usage

        for index, chat in enumerate(self.data):
            # find any blank chats and delete them
            if not chat.get("messages"):
                self.data.pop(index)

            # find any missing metadata fields and add them
            for key, default_value in self.DEFAULT_DATA.items():
                if key not in chat.keys():
                    self.data[index][key] = default_value

        # chat autoresume
        if os.path.exists(self.current_save_path) and core.config.get("core", {}).get("auto_resume_chats"):
            try:
                with open(self.current_save_path, "r") as f:
                    target_index = int(f.read())

                if target_index < len(self.data):
                    self.current = target_index
            except Exception as e:
                core.log_error("couldn't autoresume chat", e)

    def _set_current(self, index: int):
        self.current = index
        # store current index into a simple file
        with open(self.current_save_path, "w") as f:
            f.write(str(index))

    def _find_index(self, id: str):
        """find index of the chat with that ID"""
        for index, chat in enumerate(self.data):
            if chat.get("id", "").upper() == id.upper():
                return index

        return None

    async def new(self, category: str = "general", title: str = ""):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        self.data.append({
            "id": str(ulid.ULID())[:8],
            "title": title,
            "category": category,
            "tags": [],
            "messages": [],
            "custom_data": {},
            "created": now,
            "updated": now
        })
        index = len(self.data) - 1
        self._set_current(index)

        self.data.save()
        return True
    async def clear(self):
        if self.current is None:
            return False

        self.data[self.current]["messages"] = []
        await self.save()

        return True
    async def delete(self, id: str):
        """delete an entire chat"""

        index = self._find_index(id)

        if index is None:
            return False

        self.data.pop(index)
        self.data.save()

        # Adjust current index if needed
        if self.current == index:
            # Deleted the current chat - reset or move to previous
            self._set_current(min(index, len(self.data) - 1) if self.data else None)
        elif self.current > index:
            # Current was after deleted item, shift down
            self.current -= 1

        return self.current

    async def save(self):
        if self.current is None:
            await self.new()

        return self.data.save()
    async def load(self, id: str):
        index = self._find_index(id)

        if index is None:
            return False

        self._set_current(index)

        return True

    async def get_all(self):
        """returns all chats in the storage"""
        return self.data

    async def get_title(self):
        if self.current is None:
            return None
        return self.data[self.current].get("title")

    async def set_title(self, title: str):
        if self.current is None:
            return False

        self.data[self.current]["title"] = title
        await self.save()
        return True

    async def set_category(self, category: str):
        if self.current is None:
            return False

        self.data[self.current]["category"] = category
        await self.save()
        return True
    async def get_category(self):
        if self.current is None:
            return False
        return self.data[self.current].get("category", "")
    async def get_categories(self):
        collected_categories = []
        for chat in self.data:
            if chat.get("category") not in collected_categories:
                collected_categories.append(chat.get("category"))
            continue
        return collected_categories

    async def get_data(self, data_key: str = None):
        if self.current is None:
            return False

        if not data_key:
            return self.data[self.current].get("custom_data", {})

        # return the data, or None if not found
        return self.data[self.current].get("custom_data", {}).get(data_key, None)
    async def set_data(self, data_key: str, data_value):
        if self.current is None:
            return False

        self.data[self.current]["custom_data"][data_key] = data_value
        self.data.save()
        return True

    async def set_tags(self, tags: list):
        if self.current is None:
            return False

        self.data[self.current]["tags"] = tags
        await self.save()
        return True

    async def get_tags(self):
        if self.current is None:
            return False

        return self.data[self.current].get("tags", [])

    async def add_tag(self, tag: str):
        if self.current is None:
            return False

        if tag not in self.data[self.current]["tags"]:
            self.data[self.current]["tags"].append(tag)
            await self.save()
            return True

        return False

    async def pop_tag(self, tag: str):
        if self.current is None:
            return False

        if tag in self.data[self.current]["tags"]:
            self.data[self.current]["tags"].remove(tag)
            await self.save()
            return True

        return False

    async def get(self):
        """get message history of current chat"""
        if self.current is None:
            return None

        return self.data[self.current].get("messages", [])
    async def get_id(self):
        if self.current is None:
            return None

        return self.data[self.current].get("id", None)

    async def set(self, messages: list):
        """overwrite message history of current chat"""
        if self.current is None:
            await self.new()

        self.data[self.current]["messages"] = messages
        await self.save()
        return True
    async def add(self, message: dict, temporary = False):
        """add message to current chat"""
        if self.current is None:
            await self.new()

        if not self.data[self.current]["title"].strip():
            # auto-set title
            msg_content = self.channel._extract_content(message)
            if isinstance(msg_content, str):
                self.data[self.current]["title"] = msg_content[:100]+".." if len(msg_content) > 100 else msg_content
            else:
                # this happens when the user uploads a media file. don't set that as a title, lol
                pass

        # if temporary, set the flag. gets handled in self.trim()
        if temporary:
            message["temporary"] = True

        await self.trim() # automatically trim chat history
        await self._insert_blank_user_msg(message)
        self.data[self.current]["messages"].append(message)
        index = len(self.data[self.current]["messages"]) - 1

        await self.save()
        return index
    async def pop(self, index: int = None):
        """pop message from current chat"""
        if self.current is None:
            await self.new()

        self.data[self.current]["messages"].pop(index)
        index = len(self.data[self.current]["messages"]) - 1
        await self.save()
        return index

    async def trim(self, max_messages: int = None, max_tokens: int = None, num_tokens: int = None):
        """trims chat history to keep token consumption low"""
        if not max_messages:
            max_messages = int(core.config.get("api").get("max_messages", 200))
        if not max_tokens:
            max_tokens = int(core.config.get("api").get("max_context", 8192))

        messages = await self.get()
        if not messages:
            return 0 # no messages, so length is 0

        # get rid of temporary messages
        for index, msg in enumerate(messages):
            if msg.get("temporary"):
                await self.pop(index)

        if not num_tokens:
            # fall back to counting messages list using tiktoken
            num_tokens = await self.count_tokens()

        # re-fetch messages, cuz we popped
        messages = await self.get()

        request_too_big = False
        context_trimmed = False
        tokens_exceeded = (num_tokens >= max_tokens)
        message_count_exceeded = (len(messages) >= max_messages)
        num_tokens = await self.count_tokens()

        # need to recalculate it cuz this is a while loop
        while len(messages) >= max_messages or num_tokens >= max_tokens:
            # pop!
            await self.pop(0)

            # keep re-fetching
            messages = await self.get()
            if not messages:
                request_too_big = True
                # we've exhausted all messages. handle it later in this function
                break

            # keep recalculating tokens
            num_tokens = await self.count_tokens()

            if request_too_big:
                # the entire thing was too big including user's input! inform them
                await self.channel.announce("Your request exceeds the max amount of tokens allowed. Please send a smaller request!", "error")
            elif message_count_exceeded:
                await self.channel.announce(f"You exceeded the max amount of messages set in your settings! Context size trimmed.\n\nAmount of messages: {len(messages)}\nMax messages allowed: {max_messages}", "error")
            elif context_trimmed:
                await self.channel.announce("Input was too large! Context size trimmed.\n\nSent tokens: {num_tokens}\nMax allowed tokens: {max_tokens}", "error")
        return len(messages) <= max_messages

    async def _insert_blank_user_msg(self, message: dict):
        messages = await self.get()

        if (
            # if we have anything at all in the messages array
            messages and
            # and the last message was an assistant message
            messages[-1].get("role") == "assistant" and
            # and that last assistant message didn't have toolcalls
            not messages[-1].get("tool_calls") and
            # and the message we're about to post is an assistant message
            message.get("role") == "assistant"
        ):
            # according to openAI spec, consecutive assistant messages
            # are not allowed. so we enforce it here

            # assistants are allowed to output after a tool role message
            # but not after their own message..
            await self.add({"role": "user", "content": "[SYSTEM_TICK]"})
        return True

    async def count_tokens(self, messages: list = None) -> int:
        """
        Counts tokens locally using tiktoken.
        Used as a fallback if the API doesn't return usage data.
        """
        # if we have API token usage results (happens in core/channel.py),
        # just return that
        if self.token_usage > 0:
            return self.token_usage

        # otherwise fall back to counting with tiktoken

        import tiktoken
        try:
            # Try to get the specific tokenizer for the model (e.g. gpt-4)
            encoding = tiktoken.encoding_for_model(self.channel.manager.API._model)
        except KeyError:
            # Fallback to a standard encoding for unknown/custom models
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = 0
        _messages = messages if messages else await self.get()
        if not _messages:
            return 0

        for message in _messages:
            # OpenAI message format overhead is ~4 tokens per message
            # <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            for key, value in message.items():
                if value and isinstance(value, str):
                    # if it's just a normal text message, count tokens using its contents
                    num_tokens += len(encoding.encode(value))
                elif value and isinstance(value, list):
                    # if its multimodal, skip all non-text content because we filter that out when using context.get()
                    for part in value:
                        part_text = part.get("text", None)
                        if isinstance(part, dict) and part_text:
                            num_tokens += len(encoding.encode(part_text))

        # Add 2-3 tokens for the assistant priming at the end
        num_tokens += 2
        return int(num_tokens)
