import core
import ulid
import datetime
import os

import tiktoken

# TODO: split chat index from messages array into two seperate files, to vastly improve speed when saving/loading chats

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
        self.token_encoding = None
        self.model_name = None

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
                self.channel.log_error("couldn't autoresume chat", e)

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

        new_id = str(ulid.ULID())[-8:] # so it turns out truncating the ULID from the front can lead to identical id's.. yikes
        self.data.append({
            "id":  new_id,
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

        # don't immediately save, to avoid lag when creating a new chat
        # handle saving later on
        #self.data.save()

        # start a system prompt warmup so that the response is instant (if the user types slowly... lol)
        #await self.channel.manager.API.start_prompt_warmup(notify=core.debug)

        return new_id
    async def clear(self):
        if self.current is None:
            return False

        self.data[self.current]["messages"] = []
        
        # Reset token_usage since we're clearing the chat
        # API token usage is only valid for the exact context that was sent
        await self.set_token_usage(0)
        self.using_api_token_data = False
        
        await self.save()

        # start a system prompt warmup so that the response is instant (if the user types slowly... lol)
        #await self.channel.manager.API.start_prompt_warmup(notify=core.debug)

        return True

    async def delete(self, id: str):
        """delete an entire chat"""

        index = self._find_index(id)

        if index is None:
            return False

        self.data.pop(index)
        self.data.save()

        # Adjust current index if needed
        if self.current is not None:
            if self.current == index:
                # Deleted the current chat - reset or move to previous
                self._set_current(min(index, len(self.data) - 1) if self.data else None)
            elif self.current > index:
                # Current was after deleted item, shift down
                self.current -= 1

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

        if index is None or self.current == index:
            return False

        self._set_current(index)

        # start a prompt warmup using this chat's data
        # try:
        #     await self.channel.manager.API.start_prompt_warmup(context=await self.channel.context.get(), notify=core.debug)
        # except Exception as e:
        #     self.channel.log("core", f"failure while sending prompt warmup to API: {core.detail_error(e)}")

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

    async def get_chat(self):
        """
        gets the entire current chat. this is why i need to split the messages into a seperate object... this is getting confusing
        unfortunately i need to finish work on the webui first before i improve chat.py, because
        a lot of stuff across the framework depends on the chat class
        and so, will break all over the place if i remove .get() in favor of .messages.get()
        """
        if self.current is None:
            await self.new()

        return self.data[self.current]

    async def get_id(self):
        if self.current is None:
            return await self.new()

        return self.data[self.current].get("id", None)

    # ----------------------------
    # new, more sane method names
    # just aliases for now
    # as a final structure i want chat.messages.add, chat.messages.edit, and so on,
    # but there's no time right now
    # ----------------------------
    async def get_messages(self):
        return await self.get()

    async def set_messages(self, messages):
        return await self.set(messages)

    async def get_message(self, index: int):
        if not self.current:
            await self.new()

        messages = self.data[self.current]["messages"]

        if index > len(messages):
            return None

        return messages[index]

    async def add_message(self, message: dict, cmd=False, ghost = False):
        return await self.add(message, cmd=cmd, ghost=ghost)

    async def edit_message(self, index, message: dict):
        return await self.edit(index, message)

    async def delete_message(self, index):
        return await self.pop(index)

    async def delete_all_messages_after(self, index):
        return await self.delete_from(index)

    async def get_last_message_with_role(self, role: str, cutoff_index: int = None):
        if not self.current:
            return False

        # get last message by that role
        messages = await self.get()

        # if we have a "cutoff index",
        # it means we have to search backwards
        # from that index
        # which is very useful for, say,
        # regenerating a message
        # because we can target the last user message
        # before the cutoff index

        if len(messages) == 1:
            # just return the first index
            return 0

        if cutoff_index is not None:
            start_index = cutoff_index
        else:
            # Start at the very end
            start_index = len(messages)

        for index in range(start_index, -1, -1):
            if index >= len(messages):
                continue

            message = messages[index]
            if message.get("role") == role:
                return index

        return -1

    # ----------------------------------------------------------------------------
    # OLD, DEPRECATED METHODS BELOW
    # ----------------------------------------------------------------------------
    # these all apply to messages, not the chat itself,
    # and yet i named them in a way where it's really confusing whether you're
    # interacting with a chat or with the messages
    # so i'm keeping these for now, to maintain compatibility
    # with user modules and some parts of the framework,
    # but i plan to slowly migrate to more sane names
    # ----------------------------------------------------------------------------

    async def get(self, index = None):
        """get message history of current chat"""
        if self.current is None:
            await self.new()

        messages = self.data[self.current].get("messages", [])

        return messages

    async def delete_from(self, index: int):
        """
        Deletes all messages below a certain index
        """
        if self.current is None:
            return False

        messages = await self.get()
        if not messages:
            return False

        # return all messages up to and including the target message
        new_messages = messages[:index+1]

        await self.set(new_messages)
        return True

    async def set(self, messages: list):
        """overwrite message history of current chat"""
        if self.current is None:
            await self.new()

        self.data[self.current]["messages"] = messages
        await self.save()
        return True

    async def add(self, message: dict, cmd=False, ghost = False):
        """add message to current chat"""
        if self.current is None:
            await self.new()

        # make a copy so we don't modify the original reference
        new_message = message.copy()

        if not self.data[self.current]["title"].strip():
            # auto-set title
            msg_content = self.channel._extract_content(new_message)
            if isinstance(msg_content, str):
                self.data[self.current]["title"] = msg_content[:100]+".." if len(msg_content) > 100 else msg_content
            else:
                # this happens when the user uploads a media file. don't set that as a title, lol
                pass

        # if marked as a ghost message, set the flag. gets handled in self.trim()
        # ghost messages are invisible to the AI
        if ghost:
            new_message["ghost"] = True

        if cmd:
            # if the message is a command (or command response), mark it as such
            new_message["is_cmd"] = True

        # inject any special messages coming from on_message_inject() in modules, such as timestamps
        injections = []
        if message.get("role") == "user":
            for module_name, module in self.channel.manager.modules.items():
                if hasattr(module, 'on_message_inject'):
                    try:
                        injection = await module.on_message_inject()
                        if injection:
                            injections.append(injection)
                    except Exception as e:
                        self.channel.log("module error", f"{module.name}: in on_message_inject(): {core.detail_error(e)}")

            if injections:
                new_message["injection"] = "\n\n".join(injections)

        self.data[self.current]["messages"].append(new_message)

        index = len(self.data[self.current]["messages"]) - 1
        await self.save()
        return True

    async def edit(self, index: int, message):
        """edit message by its index"""
        if self.current is None:
            return False

        if index >= len(self.data[self.current]["messages"]):
            return False

        self.data[self.current]["messages"][index] = message
        await self.save()

    async def pop(self, index: int = None):
        """pop message from current chat"""
        if self.current is None:
            await self.new()

        if index is None:
            index = -1

        self.data[self.current]["messages"].pop(index)
        index = len(self.data[self.current]["messages"]) - 1
        await self.save()

        return index

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

    def _count_text_tokens(self, text: str) -> int:
        """Helper to encode text using tiktoken or fallback to character heuristic"""
        if not text:
            return 0

        if self.token_encoding:
            try:
                return len(self.token_encoding.encode(text))
            except Exception:
                # Fallback if encoding specifically fails
                return len(text) // 4
        else:
            # Fallback: 1 token is roughly 4 characters for most English text
            return len(text) // 4

    async def count_tokens(self, messages: list = None):
        """
        Counts token usage locally using tiktoken (with fallback)
        """
        num_tokens = 0
        _messages = messages or await self.channel.context.get(system_prompt=True, end_prompt=True)

        if not _messages or isinstance(_messages, core.api.APIError):
            return 0

        # only set the tiktoken encoder if the model changed
        # model name changes when connecting for the first time
        # or when swapping models
        model_name = self.channel.manager.API.get_model()
        if model_name != self.model_name:
            self.model_name = model_name

            try:
                self.token_encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                self.token_encoding = tiktoken.get_encoding("cl100k_base")
            except Exception as e:
                # If tiktoken fails to load (e.g. no internet and no cache), we set to None
                # _count_text_tokens then uses a character-based fallback
                self.token_encoding = None
                self.channel.log_error("[TIKTOKEN] Falling back on character-based token counting.", e)
                pass

        for message in _messages:
            # Conservative token counting:
            # - 3 tokens for message overhead (OpenAI format: <im_start>role\ncontent<im_end>\n)
            num_tokens += 3

            # Count content
            if "content" in message:
                content = message["content"]
                if isinstance(content, str):
                    num_tokens += self._count_text_tokens(content)
                elif isinstance(content, list):
                    # if its multimodal, skip all non-text content because we filter that out when using context.get()
                    for part in content:
                        if isinstance(part, dict):
                            part_text = part.get("text")
                            if isinstance(part_text, str):
                                num_tokens += self._count_text_tokens(part_text)

            # If there's a name, add it (it's part of the message)
            if "name" in message and isinstance(message["name"], str):
                num_tokens += self._count_text_tokens(message["name"])

            # Count reasoning content if present
            if "reasoning_content" in message and isinstance(message["reasoning_content"], str):
                num_tokens += self._count_text_tokens(message["reasoning_content"])

            # Count tool calls if present (in assistant messages)
            if "tool_calls" in message and isinstance(message["tool_calls"], list):
                for tool_call in message["tool_calls"]:
                    if isinstance(tool_call, dict):
                        # Count the call ID
                        if "id" in tool_call and isinstance(tool_call["id"], str):
                            num_tokens += self._count_text_tokens(tool_call["id"])
                        # Count the type
                        if "type" in tool_call and isinstance(tool_call["type"], str):
                            num_tokens += self._count_text_tokens(tool_call["type"])
                        # Count the function name and arguments
                        if "function" in tool_call and isinstance(tool_call["function"], dict):
                            function = tool_call["function"]
                            if "name" in function and isinstance(function["name"], str):
                                num_tokens += self._count_text_tokens(function["name"])
                            if "arguments" in function and isinstance(function["arguments"], str):
                                num_tokens += self._count_text_tokens(function["arguments"])

            # Count tool_call_id if present (in tool result messages)
            if "tool_call_id" in message and isinstance(message["tool_call_id"], str):
                num_tokens += self._count_text_tokens(message["tool_call_id"])

        # Add 1 token for final assistant priming (conservative)
        num_tokens += 1

        return int(num_tokens)
