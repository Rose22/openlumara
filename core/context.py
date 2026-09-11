import core
import json

class Context:
    # special message type (not intended to be added to context) that
    # will cause context.get() to cut off messages before this cutoff point
    SUMMARIZATION_CUTOFF = {"_metadata": {"signal": "SUMMARIZATION_CUTOFF"}}

    def __init__(self, channel):
        self.channel = channel
        self.model_name = None
        self.using_api_token_data = False
        self.token_encoding = None

        # UI-agnostic chat history system - save/load context windows from save file!
        self.chat = core.chat.Chat(self.channel)

    async def get(self, system_prompt=True, end_prompt=True, history=True, prevent_recursion=False):
        """
        builds the full context window using system prompt + message history + end prompt
        to the API, we send this full context.

        to frontend channels, we send only the message history part of the context (context.chat.messages.get()),
        without the system prompt and without the modifications we do to it such as the endprompt.

        context must ALWAYS follow this strict turn order: system->user->assistant->user->assistant->user->...
        """
        if not self.channel.manager.API.connected:
            # attempt to connect
            result = await self.channel.manager.API.connect()
            if result is not True:
                self.channel.log("api", str(result))
                return result

        # Configuration
        max_messages = int(core.config.get("api").get("max_messages", 200))
        max_tokens = int(core.config.get("api").get("max_context", 16768))
        system_role = "system" if not self.channel.manager.API.supports_developer_role else "developer"
        dev_role = "developer" if self.channel.manager.API.supports_developer_role else "user"

        # 1. Prepare Components
        system_msg = []
        if system_prompt:
            try:
                content = await self.channel.manager.get_system_prompt()
            except Exception as e:
                self.channel.log_error("Error while getting system prompt", e)

            if content:
                system_msg = [{"role": system_role, "content": content}]

        messages = []
        if history:
            # Get history from the chat (the full, untrimmed version)
            # create a shallow copy of it by doing a list comprehension
            messages = [dict(msg) for msg in await self.chat.messages.get()]

            # we need to support chat summarization without losing the user-facing end of chat history
            # so that we can cut context without actually losing our logs..

            # so, i'm using a special entry in the messages array that serves as a cutoff point
            # from which to actually return the chat history

            # find the last occurence of it and return only the messages from that point onward
            for i in range(len(messages) - 1, -1, -1):
                if messages[i].get("_metadata", {}).get("signal") == "SUMMARIZATION_CUTOFF":
                    messages = [{"role": "user", "content": "Summarize our chat so far."}] + messages[i + 1:]
                    break

            # Remove ghost messages and signal messages from history
            messages = [msg for msg in messages if not msg.get("_metadata", {}).get("ghost") and not msg.get("_metadata", {}).get("signal")]

            # Strip invalid assistant messages (those without content or tool calls)
            messages = [
                msg for msg in messages
                if not (msg.get("role") == "assistant" and not msg.get("content") and not msg.get("tool_calls"))
            ]

            # If disabled, remove reasoning from all prior messages
            if not core.config.get("model", "keep_reasoning_in_context"):
                messages = [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]

            if core.config.get("model", "only_preserve_reasoning_for_current_agentic_loop"):
                # TODO: i really need to make a more user friendly UI for core settings, that matches the UX of module/channel settings...
                # that name is ridiculous

                # strip reasoning from tool calls prior to the current agentic loop
                loop_idx = self.channel.agentic_loop_start
                messages[:loop_idx] = [
                    {k: v for k, v in m.items() if k != "reasoning_content"}
                    if "tool_calls" in m else m
                    for m in messages[:loop_idx]
                ]

            # Apply max_messages limit to history first
            if len(messages) > max_messages:
                messages = messages[-max_messages:]

            # Strip multimodal data from all messages except the last one to save tokens
            if messages:
                for i in range(len(messages) - 1):
                    msg = messages[i]
                    if msg.get("role") in ("tool", "tool_calls"):
                        # Don't mess with tool calls
                        continue

                    content = msg.get("content")
                    if isinstance(content, list):
                        # Keep only the text parts of the message
                        text_parts = [
                            part for part in content
                            if isinstance(part, dict) and part.get("type") == "text"
                        ]
                        # If stripping leaves nothing, convert to a placeholder string
                        # to avoid sending an empty content list (which some APIs reject)
                        if text_parts:
                            msg["content"] = text_parts
                        else:
                            msg["content"] = "[multimedia content]"
                    elif isinstance(content, str):
                        pass
                    # Non-string, non-list content is left as-is (don't silently drop messages)


        end_msg = []
        if end_prompt:
            histend = await self.channel.manager.get_end_prompt(prevent_recursion=prevent_recursion)
            if histend:
                end_msg = [{"role": dev_role, "content": histend}]

        # now we inject anything modules want to inject into the user messages
        for message in messages:
            metadata = message.get("_metadata")
            if not metadata:
                continue

            if metadata.get("injection"):
                if message.get("role") == "user":
                    content = message.get("content")
                    if content and isinstance(content, str):
                        message["content"] += f"\n\n{metadata['injection']}"

        # remove any non-standard (metadata) fields from the messages
        # so that we can cleanly send it to the API
        # we cant just remove only the _metadata field because old chat history used to use metadata fields
        # straight on the message object itself without containing it into a _metadata array,
        # so we need to be aggressive here
        approved_keys = ["role", "content", "reasoning_content", "tool_calls", "tool_call_id", "function_call", "tool"]
        messages = [{k: v for k, v in msg.items() if k in approved_keys} for msg in messages]

        # enforce correct turn order
        # system -> user -> assistant -> user -> assistant -> ...
        # assistant -> tool -> assistant is VALID (tool use flow)
        # assistant -> assistant is INVALID (needs spacer)
        if messages:
            enforced_messages = []
            for msg in messages:
                if enforced_messages:
                    last_role = enforced_messages[-1].get("role")
                    current_role = msg.get("role")

                    # assistant -> assistant: insert user spacer
                    if last_role == "assistant" and current_role == "assistant":
                        enforced_messages.append({"role": "user", "content": " "})
                    # user -> user: insert assistant spacer
                    elif last_role == "user" and current_role == "user":
                        enforced_messages.append({"role": "assistant", "content": " "})
                    # tool -> user: insert assistant spacer (tool result without assistant response)
                    elif last_role == "tool" and current_role == "user":
                        enforced_messages.append({"role": "assistant", "content": " "})
                    # user -> tool: insert assistant spacer (tool call without tool result)
                    elif last_role == "user" and current_role == "tool":
                        enforced_messages.append({"role": "assistant", "content": " "})

                enforced_messages.append(msg)

            messages = enforced_messages

        # 2. Build and Trim Context
        # We combine them to check the total token count

        # Count tool tokens separately (tools are passed as a separate API parameter, not as messages)
        tool_tokens = 0
        if self.channel.manager.tools:
            tool_tokens = await self.count_tokens(self.channel.manager.tools)

        # then combine it all
        full_context = system_msg + messages + end_msg
        
        # Calculate current token count (includes tools + context)
        current_tokens = await self.count_tokens(full_context) + tool_tokens

        # Leave a small buffer (5%) to avoid hitting exact limit
        effective_max_tokens = int(max_tokens * 0.95)
        
        # If we are over the limit, trim the history (the middle part).
        # We don't trim the system prompt or the end prompt as they are essential.
        # Use binary search to find the optimal trim point efficiently.
        if current_tokens > effective_max_tokens and messages:
            # Reserve tokens for the last user message so it always fits
            reserved_tokens = 0
            if messages and messages[-1].get("role") == "user":
                reserved_tokens = await self.count_tokens([messages[-1]])
            
            # Reduce the effective max by the reserved amount
            effective_max_with_reserve = effective_max_tokens - reserved_tokens
            
            # Binary search: find the minimum number of messages to remove from the front
            lo, hi = 0, len(messages)
            best_trim = len(messages)  # worst case: remove everything

            while lo <= hi:
                mid = (lo + hi) // 2
                trimmed = messages[mid:]
                candidate_context = system_msg + trimmed + end_msg
                tokens = tool_tokens + await self.count_tokens(candidate_context) + reserved_tokens

                if tokens <= effective_max_tokens:
                    best_trim = mid
                    hi = mid - 1
                else:
                    lo = mid + 1

            messages = messages[best_trim:]
            full_context = system_msg + messages + end_msg
            current_tokens = tool_tokens + await self.count_tokens(full_context) + reserved_tokens

        # If we are STILL over the limit even with empty history,
        # the system prompt + end prompt alone exceed the limit, or a single message is too large.
        if current_tokens > max_tokens:
            await self.channel.push(
                f"Your system prompt of {current_tokens} tokens somehow exceeds the maximum context size of {max_tokens}! Please set a larger context size. Or disable some modules, disable system prompt insertion across modules, do whatever you can to reduce token size."
            )

            # immediately disconnect so we don't spam the API
            await self.channel.manager.API.disconnect()

            return None

        return full_context

    async def get_size(self):
        """basically just a fancy display of current token use, used by the `/status` command, and can optionally be used by other parts of the framework"""

        # we're using self.get() here because it dynamically trims message history,
        # and chat.messages.get() would instead return the ENTIRE history without trimming,
        # which would be an inaccurate count
        message_history = await self.get(system_prompt=False, end_prompt=False, history=True)
        sysprompt = await self.get(system_prompt=True, end_prompt=False, history=False)
        histend = await self.get(system_prompt=False, end_prompt=True, history=False)
        
        # now we count the tokens for each part of the context
        sysprompt_size_tokens = await self.count_tokens(sysprompt)
        sysprompt_size_words = len(str(sysprompt).split())
        
        message_hist_size_tokens = await self.count_tokens(message_history)
        message_hist_size_words = len(str(message_history).split())
        
        histend_size_tokens = await self.count_tokens(histend)
        histend_size_words = len(str(histend).split()) if histend else 0

        tool_array_size_tokens = await self.count_tokens(self.channel.manager.tools)
        tool_array_size_words = len(str(self.channel.manager.tools).split())

        # get amount of tools active
        tools_amount = len(self.channel.manager.tools)

        combined_size_words = tool_array_size_words + sysprompt_size_words + message_hist_size_words + histend_size_words

        token_usage = await self.get_total_tokens()

        return {
            "system prompt size": f"{sysprompt_size_tokens} tokens | {sysprompt_size_words} words",
            "tools": f"{tools_amount} tools active | {tool_array_size_tokens} tokens | {tool_array_size_words} words",
            "message history size": f"{message_hist_size_tokens} tokens | {message_hist_size_words} words",
            "end prompt size": f"{histend_size_tokens} tokens | {histend_size_words} words",
            "total size": f"{token_usage} tokens | {combined_size_words} words",
        }

    def _count_text_tokens(self, text: str) -> int:
        """does the actual token-counting by counting characters"""

        if not text:
            return 0
        
        # 1 token is roughly 4 characters for most English text
        return len(text) // 4

    async def get_total_tokens(self):
        """returns the total amount of tokens taken up by the prompt + the tools array"""

        context = await self.get()
        if not context:
            return 0

        num_tokens = await self.count_tokens(context)

        # add the total token count of the tools array
        if self.channel.manager.tools:
            num_tokens += await self.count_tokens(self.channel.manager.tools)

        return num_tokens

    async def count_tokens(self, data):
        """
        the function that gets called all over the framework to count the token usage of any data.
        converts the data into a json string, then uses _count_text_tokens() to do the actual counting
        """
        num_tokens = 0

        if isinstance(data, core.api.APIError):
            return 0

        try:
            if isinstance(data, list):
                # this is likely an array of messages

                # count only the text tokens, since API's exempt multimodal content from token limits,
                # and we auto remove all previous multimodal content from context when passing to the API,
                # sending only the current message's multimodal content (such as an image)

                # first i coded this function by hand using a for loop that copied each message and stripped it of any non-text content, 
                # then i asked my local AI for a more compact and performance friendly way to do it.
                # now that's a good way to use AI coding, imho :)
                # thanks Qwen3.6-35B!
                cleaned_messages = [
                    {**msg, "content": [item for item in (msg.get("content") or []) if item.get("type") == "text"]}
                    if isinstance(msg.get("content"), list)
                    else msg
                    for msg in data
                ]
                data_str = json.dumps(cleaned_messages)
            else:
                data_str = json.dumps(data)
        except Exception as e:
            raise Exception(f"Error while counting tokens: {core.detail_error(e)}")

        num_tokens = self._count_text_tokens(data_str)
        return num_tokens
