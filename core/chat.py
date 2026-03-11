import core
import ulid
import datetime

class Chat:
    """contains openAI messages array, and can save and load sets of messages from files"""
    def __init__(self, channel):
        self.data = core.storage.StorageList(f"{channel.name}_chats", "json")
        self.channel = channel
        self.current = None

    def _find_index(self, id: str):
        """find index of the chat with that ID"""
        for index, chat in enumerate(self.data):
            if chat.get("id", "").upper() == id.upper():
                return index

        return None

    async def new(self, title: str = "New chat"):
        """create a new chat"""
        now = datetime.datetime.utcnow().isoformat()

        self.data.append({
            "id": str(ulid.ULID())[:8],
            "title": title,
            "messages": [],
            "created": now,
            "updated": now
        })
        index = len(self.data) - 1
        self.current = index

        self.data.save()
        return True
    async def clear(self):
        index = self._find_index(id)

        if not index:
            return False

        self.data[index]["messages"] = []
        self.save()

        return True
    async def delete(self, id: str):
        """delete an entire chat"""

        index = self._find_index(id)

        if not index:
            return False

        return self.data.pop(index)

    async def save(self):
        if not self.current:
            await self.new()

        return self.data.save()
    async def load(self, id: str):
        index = self._find_index(id)

        if not index:
            return False

        await self.set(self.data[index].get("messages", []))
        self.current = index
        return True
    async def get_all(self):
        """returns all chats in the storage"""
        return self.data

    async def get_title(self):
        if not self.current:
            return None
        return self.data[self.current].get("title")

    async def set_title(self, title: str):
        if not self.current:
            return None

        self.data[self.current]["title"] = title
        await self.save()
        return True

    async def get(self):
        """get message history of current chat"""
        if not self.current:
            return None

        return self.data[self.current].get("messages", [])
    async def get_id(self):
        if not self.current:
            return None

        return self.data[self.current].get("id", None)

    async def set(self, messages: list):
        """overwrite message history of current chat"""
        if not self.current:
            await self.new()

        self.data[self.current]["messages"] = messages
        await self.save()
        return True
    async def add(self, message: dict, temporary = False):
        """add message to current chat"""
        if not self.current:
            await self.new()

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
        if not self.current:
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

        # get rid of temporary messages
        for index, msg in enumerate(await self.get()):
            if msg.get("temporary"):
                self.pop(index)

        if not num_tokens:
            # fall back to counting messages list using tiktoken
            num_tokens = await self.count_tokens()

        request_too_big = False
        context_trimmed = False
        tokens_exceeded = (num_tokens >= max_tokens)
        message_count_exceeded = (len(await self.get()) >= max_messages)
        num_tokens = await self.count_tokens()

        # need to recalculate it cuz this is a while loop
        messages = await self.get()
        while len(messages) >= max_messages or num_tokens >= max_tokens:
            self.pop(0)
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
            # and the last message was not a user or tool response message
            messages[-1].get("role") not in ("user", "tool") and
            # and the last message was also not an assistant message with toolcalls
            not messages[-1].get("tool_calls") and
            # and the message we're about to post isn't by the user role
            message.get("role") != "user"
        ):
            # ensure message turn order is correct
            # assistants are allowed to output after a tool role message
            # but not after their own message..
            self.chat.add({"role": "user", "content": "[SYSTEM_TICK]"})
        return True

    async def count_tokens(self, messages: list = None) -> int:
        """
        Counts tokens locally using tiktoken.
        Used as a fallback if the API doesn't return usage data.
        """
        import tiktoken
        try:
            # Try to get the specific tokenizer for the model (e.g. gpt-4)
            encoding = tiktoken.encoding_for_model(self.channel.manager.API._model)
        except KeyError:
            # Fallback to a standard encoding for unknown/custom models
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = 0
        _messages = messages if messages else await self.get()
        for message in _messages:
            # OpenAI message format overhead is ~4 tokens per message
            # <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            for key, value in message.items():
                if value:
                    num_tokens += len(encoding.encode(str(value)))

        # Add 2-3 tokens for the assistant priming at the end
        num_tokens += 2
        return int(num_tokens)
