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
        "token_usage": 0
    }

    """contains openAI messages array, and can save and load sets of messages from files"""
    def __init__(self, channel):
        self.data = core.storage.StorageList(f"{channel.name}_chats", "json")
        self.channel = channel
        self.current = None
        self.current_save_path = os.path.join(core.get_data_path(), f"{self.channel.name}_current_chat")
        self.using_api_token_data = False # gets instantly set to True upon first receive of token usage data

        for index in range(len(self.data) - 1, -1, -1):
            chat = self.data[index]
            messages = chat.get("messages", [])
            
            # find any blank chats and delete them
            if not messages:
                self.data.pop(index)
            # find chats that only contain command/responses and delete them
            elif self._is_command_only(messages):
                self.data.pop(index)
            # find any missing metadata fields and add them
            else:
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

    def _is_command_only(self, messages):
        """Check if a messages array contains only user commands and command responses"""
        if not messages:
            return False
        
        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")
        
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if not isinstance(content, str):
                # this is definitely not a command or command response lol
                continue

            # User command messages start with the configured command prefix
            if role == "user" and content.strip().startswith(cmd_prefix):
                continue
            # Command response messages start with [Command Output]:
            elif role == "assistant" and content.strip().startswith("[Command Output]:"):
                continue
            else:
                # Found a message that isn't a command or response
                return False
        return True

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

    async def new(self, category: str = "general", title: str = "", metadata = {}):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        self.data.append({
            "id": str(ulid.ULID())[:8],
            "title": title,
            "category": category,
            "tags": [],
            "messages": [],
            "custom_data": metadata,
            "created": now,
            "updated": now
        })
        index = len(self.data) - 1
        self._set_current(index)

        await self.set_token_usage(0)
        self.using_api_token_data = False

        self.data.save()
        return True
    async def clear(self):
        if self.current is None:
            return False

        self.data[self.current]["messages"] = []
        
        # Reset token_usage since we're clearing the chat
        # API token usage is only valid for the exact context that was sent
        await self.set_token_usage(0)
        self.using_api_token_data = False
        
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
            return True  # no messages to trim

        # get rid of temporary messages first
        for index, msg in enumerate(messages):
            if msg.get("temporary"):
                await self.pop(index)

        # re-fetch messages after removing temporary ones
        messages = await self.get()
        if not messages:
            return True

        # Calculate current token count if not provided
        if num_tokens is None:
            num_tokens = await self.get_token_usage()

        # Leave a small buffer (5%) to avoid hitting exact limit
        token_buffer = max_tokens * 0.05
        effective_max_tokens = max_tokens - token_buffer

        # Check if we need to trim
        needs_trimming = False
        if len(messages) > max_messages:
            needs_trimming = True
        elif num_tokens > effective_max_tokens:
            needs_trimming = True

        if not needs_trimming:
            return True

        # Track if we had to trim due to token limit
        trimmed_due_to_tokens = num_tokens > effective_max_tokens
        trimmed_due_to_messages = len(messages) > max_messages

        # Trim messages until we're under limits
        while messages and (len(messages) > max_messages or num_tokens > effective_max_tokens):
            # Remove the oldest message
            await self.pop(0)

            # Update messages and token count
            messages = await self.get()
            if not messages:
                # All messages removed - this shouldn't happen unless single message exceeds limit
                break

            num_tokens = await self.count_tokens()

        # Check if we still have a problem after trimming
        if messages:
            num_tokens = await self.count_tokens()
            if num_tokens > max_tokens:
                # Even after trimming all but current message, we're over limit
                # This means the current message itself is too large
                await self.channel.announce(
                    "Your request exceeds the maximum token limit. Please send a smaller message!",
                    "error"
                )
                return False

        return True

    async def _insert_blank_user_msg(self, message: dict):
        messages = await self.get()

        if (
            # if we have anything at all in the messages array
            messages and
            # and the last message was an assistant message
            messages[-1].get("role") == "assistant" and
            # and the message we're about to post is an assistant message
            message.get("role") == "assistant"
        ):
            # according to openAI spec, consecutive assistant messages
            # are not allowed. so we enforce it here

            # assistants are allowed to output after a tool role message
            # but not after their own message..
            await self.add({"role": "user", "content": "[SYSTEM_TICK]"})
        return True

    async def get_token_usage(self):
        """
        Returns the chat's current total token usage.
        Prioritizes the API's data above all,
        but if not available, will fall back on counting locally using tiktoken
        """
        if not self.using_api_token_data:
            return await self.count_tokens()

        return self.data[self.current]["token_usage"]

    async def set_token_usage(self, usage: int):
        self.data[self.current]["token_usage"] = usage
        self.data.save()

    async def count_tokens(self, messages: list = None):
        """
        Counts token usage locally using tiktoken
        """

        import tiktoken

        # Get the model name from the API client
        model_name = None
        if hasattr(self.channel, 'manager') and hasattr(self.channel.manager, 'API'):
            model_name = self.channel.manager.API._model

        encoding = None
        try:
            # Try to get the specific tokenizer for the model (e.g. gpt-4)
            if model_name:
                encoding = tiktoken.encoding_for_model(model_name)
        except (KeyError, ValueError):
            # Fallback for unknown/custom models
            pass

        if not encoding:
            # Final fallback to cl100k_base (used by GPT-4, Claude, etc.)
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = 0
        _messages = messages or await self.channel.context.get(system_prompt=True, end_prompt=True)
        if not _messages:
            return 0

        for message in _messages:
            # Conservative token counting:
            # - 3 tokens for message overhead (OpenAI format: <im_start>role\ncontent<im_end>\n)
            # - Role is counted as part of content
            # - This is simpler and less likely to overcount than more complex formulas

            num_tokens += 3

            # Count content
            if "content" in message:
                content = message["content"]
                if isinstance(content, str):
                    num_tokens += len(encoding.encode(content))
                elif isinstance(content, list):
                    # if its multimodal, skip all non-text content because we filter that out when using context.get()
                    for part in content:
                        if isinstance(part, dict):
                            part_text = part.get("text")
                            if isinstance(part_text, str):
                                num_tokens += len(encoding.encode(part_text))

            # If there's a name, add it (it's part of the message)
            if "name" in message and isinstance(message["name"], str):
                num_tokens += len(encoding.encode(message["name"]))

            # Count reasoning content if present
            if "reasoning_content" in message and isinstance(message["reasoning_content"], str):
                num_tokens += len(encoding.encode(message["reasoning_content"]))

        # Add 1 token for final assistant priming (conservative)
        num_tokens += 1

        return int(num_tokens)
