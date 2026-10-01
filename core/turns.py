import asyncio
import json

class TurnCollector:
    """
    this takes a raw openAI messages array and turns it into a grouped list of dicts,
    where a "turn" is a group of any assistant/tool messages inbetween a user's request

    so basically, a user makes their request, then the response gets grouped into one single object
    that contains multiple messages, grouped by type (reasoning, content, toolcall, etc)

    this works for chat history (group_history) and even for streams (group_stream)

    this is a port from the old webui's frontend-only turn collection logic
    now available in the core for any channel to use :)
    """

    async def group_history(self, history):
        """
        Groups all finalized messages from history into turns.
        Returns a list of turn objects.
        """
        turns = []
        current_assistant_turn = None

        for index, msg in enumerate(history):
            role = msg.get('role')

            # add the index to the message so that it can be directly targeted no matter which turn it is in
            msg["index"] = index
            
            if role == 'user':
                if current_assistant_turn:
                    # if a user message arrives and it's currently still
                    # the assistant's turn, that means we finalize it, and move onto a new turn!
                    turns.append(current_assistant_turn)
                    current_assistant_turn = None
                
                # append the user message as a single turn. a user message is never multiple turns
                turns.append({
                    "role": "user",
                    "messages": [msg.copy()],
                    "first_message_index": index
                })
            else:
                # create the assistant turn if it doesn't already exist
                if not current_assistant_turn:
                    current_assistant_turn = {
                        "role": "assistant",
                        "first_message_index": index,
                        "messages": []
                    }

                # update the last message index.. since this is a for loop,
                # by the time we reach the last message, this will be set to the last message index
                current_assistant_turn["last_message_index"] = index
                    
                current_assistant_turn["messages"].append(msg)

        if current_assistant_turn:
            turns.append(current_assistant_turn)

        # merge tool responses into their tool calls
        for turn in turns:
            if turn["role"] != 'assistant':
                continue
            
            response_map = {}
            for msg in turn["messages"]:
                if msg.get("role") == 'tool':
                    response_map[msg["tool_call_id"]] = msg.get("content")

            for msg in turn["messages"]:
                if msg.get("tool_calls"):
                    for tool in msg["tool_calls"]:
                        if tool.get("id") in response_map:
                            tool["response"] = response_map[tool["id"]]
                        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                        # precompute the failed flag so channels don't
                        # re-parse every response just to tint a card
                        tool["failed"] = self._tool_call_failed(tool)
                        # ... and the one-line arg summary for headers
                        tool["summary"] = self._tool_call_summary(tool)

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
        # fold each assistant turn's chain into display steps so channels
        # don't re-derive the agentic-step grouping themselves.
        for turn in turns:
            if turn["role"] != "assistant":
                continue
            steps, final_messages = self.build_steps(turn["messages"])
            turn["steps"] = steps
            turn["final_messages"] = final_messages

        return turns

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # -- step model: ports of the webui frontend's chainDisplay()/
    # -- historyTurnSplit() grouping. a step = one reasoning/content run
    # -- plus the tool calls it leads to (or a tool-less thinking-only step).
    # -- steps carry precomputed "modules" display data so templates only
    # -- need to render, never to group.

    @staticmethod
    def _tool_call_failed(tool):
        # a tool call failed when its parsed response is {status: "error"}
        response = tool.get("response")
        if response is None:
            return False
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
        except (json.JSONDecodeError, TypeError):
            return False
        return isinstance(parsed, dict) and parsed.get("status") == "error"

    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
    # one-line arg summary for completed tool call headers, ported from
    # the webui frontend's toolCallArgsSummary(): the single most
    # informative argument value, paths keep their tail.
    TOOL_ARG_PRIORITY = [
        "path", "file_path", "filepath", "file", "filename", "url",
        "query", "pattern", "regex_pattern", "sub_path", "subfolder",
        "folder", "id", "name", "content", "text",
    ]

    @staticmethod
    def _truncate_arg(s):
        if len(s) <= 70:
            return s
        if "/" in s or "\\" in s:
            return ".." + s[-68:]
        return s[:69].rstrip() + ".."

    @staticmethod
    def _arg_to_string(value):
        if isinstance(value, str):
            return value
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value)
            except (TypeError, ValueError):
                return str(value)
        if value is None:
            return "null"
        if value is True:
            return "true"
        if value is False:
            return "false"
        return str(value)

    @classmethod
    def _tool_call_summary(cls, tool):
        raw = (tool.get("function") or {}).get("arguments")
        if not isinstance(raw, str):
            return ""
        try:
            args = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return ""
        if not isinstance(args, dict) or not args:
            return ""
        entries = list(args.items())
        chosen = None
        for priority_key in cls.TOOL_ARG_PRIORITY:
            hit = next(((k, v) for k, v in entries if k == priority_key), None)
            if hit:
                chosen = hit
                break
        if chosen is None:
            chosen = next(((k, v) for k, v in entries if isinstance(v, str)), entries[0])
        return "(" + cls._truncate_arg(cls._arg_to_string(chosen[1])) + ")"

    @staticmethod
    def _modules_for(tool_calls):
        # deduped per-function counts grouped by module (first token):
        # [{"module": "Coder", "actions": [{"name": "file edit", "count": 2}]}]
        counts = {}
        order = []
        for tool in tool_calls or []:
            fn = (tool.get("function") or {}).get("name")
            if not fn:
                continue
            if fn not in counts:
                counts[fn] = 0
                order.append(fn)
            counts[fn] += 1
        groups = {}
        group_order = []
        for fn in order:
            parts = fn.split("_")
            module = parts[0][:1].upper() + parts[0][1:]
            action = "_".join(parts[1:])
            if module not in groups:
                groups[module] = []
                group_order.append(module)
            existing = next((a for a in groups[module] if a["name"] == action), None)
            if existing:
                existing["count"] += counts[fn]
            else:
                groups[module].append({"name": action, "count": counts[fn]})
        return [{"module": m, "actions": groups[m]} for m in group_order]

    @staticmethod
    def _step_status(tool_calls):
        # running: some call still lacks a response. failed: every call
        # failed. thoughts: tool-less step.
        if not tool_calls:
            return "thoughts"
        if any(t.get("response") is None for t in tool_calls):
            return "running"
        if all(TurnCollector._tool_call_failed(t) for t in tool_calls):
            return "failed"
        return "done"

    @staticmethod
    def _is_final_content(msg):
        return (
            msg.get("role") == "assistant"
            and not msg.get("tool_calls")
            and isinstance(msg.get("content"), str)
            and msg.get("content", "").strip() != ""
        )

    @staticmethod
    def _segment_label(segment):
        # short human label for the collapsed Process header: the last
        # tool call as "Module: action", or what the model is busy doing
        tool_calls = segment.get("tool_calls")
        if tool_calls:
            fn = (tool_calls[-1].get("function") or {}).get("name")
            if fn:
                parts = fn.split("_")
                return parts[0][:1].upper() + parts[0][1:] + ": " + " ".join(parts[1:])
        if isinstance(segment.get("reasoning_content"), str) and segment["reasoning_content"].strip():
            return "Thinking.."
        if isinstance(segment.get("content"), str) and segment["content"].strip():
            return "writing"
        return ""

    @staticmethod
    def _has_visible_chain_content(msg):
        if msg.get("tool_calls"):
            return len(msg["tool_calls"]) > 0
        if isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip():
            return True
        if msg.get("role") == "assistant" and isinstance(msg.get("content"), str) and msg["content"].strip():
            return True
        return False

    def build_steps(self, messages):
        # split a finalized assistant turn's messages into (steps, final).
        # the last content-without-toolcalls message is the final answer;
        # everything else is the chain. reasoning riding on the final
        # answer becomes its own trailing Thoughts step (copies, the
        # stored messages are never mutated).
        final_index = -1
        for i in range(len(messages) - 1, -1, -1):
            if self._is_final_content(messages[i]):
                final_index = i
                break

        chain = []
        final = []
        for i, message in enumerate(messages):
            if i == final_index:
                if isinstance(message.get("reasoning_content"), str) and message["reasoning_content"].strip():
                    chain_copy = dict(message)
                    chain_copy["content"] = ""
                    chain.append(chain_copy)
                    final_copy = dict(message)
                    final_copy.pop("reasoning_content", None)
                    final.append(final_copy)
                else:
                    final.append(message)
            elif self._has_visible_chain_content(message):
                chain.append(message)

        steps = []
        step_num = 0
        i = 0
        while i < len(chain):
            m = chain[i]
            has_tools = bool(m.get("tool_calls"))

            if has_tools:
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(m["tool_calls"]),
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": m["tool_calls"],
                    "modules": self._modules_for(m["tool_calls"]),
                })
                i += 1
                continue

            # thought run: consecutive reasoning/content segments
            def is_thought(msg):
                return (
                    not msg.get("tool_calls")
                    and ((isinstance(msg.get("reasoning_content"), str) and msg["reasoning_content"].strip())
                         or (isinstance(msg.get("content"), str) and msg["content"].strip()))
                )
            j = i
            while j < len(chain) and is_thought(chain[j]):
                j += 1
            tool_seg = chain[j] if (j > i and j < len(chain) and chain[j].get("tool_calls")) else None

            reasoning = ""
            content = ""
            for k in range(i, j):
                if chain[k].get("reasoning_content"):
                    reasoning = (reasoning + "\n\n" if reasoning else "") + chain[k]["reasoning_content"]
                if chain[k].get("content"):
                    content = (content + "\n\n" if content else "") + chain[k]["content"]

            if tool_seg:
                # the run led to a tool call: fold it into that step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": self._step_status(tool_seg["tool_calls"]),
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": tool_seg["tool_calls"],
                    "modules": self._modules_for(tool_seg["tool_calls"]),
                })
                i = j + 1
            elif j == len(chain):
                # trailing thought run with no tool call: a thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": reasoning,
                    "content": content,
                    "tool_calls": [],
                    "modules": [],
                })
                i = j
            else:
                # thought run followed by something odd (e.g. tool-result
                # only message): keep the message as its own thoughts step
                step_num += 1
                steps.append({
                    "step": step_num,
                    "status": "thoughts",
                    "reasoning_content": m.get("reasoning_content") or "",
                    "content": m.get("content") or "",
                    "tool_calls": [],
                    "modules": [],
                })
                i += 1

        return steps, final

    async def group_stream(self, stream_generator):
        """
        this takes the raw stream generator and yields 'streaming turn' objects
        as tokens come in.

        this way, we can display each segment throughout the UI, seperately,
        using whatever layout and components we want!

        it's basically a state machine that groups tokens into segments.
        a segment is just a group of tokens of the same type.

        unlike normal streaming deltas, these tokens accumulate,
        and are meant to be used in UI's where you can fully replace the content of a UI component
        with the new content with the newly streamed tokens added

        since an assistant response can contain multiple kinds of content in sequence,
        like reasoning -> content -> tool_calls -> tool responses -> more reasoning -> final answer (reasoning+content)
        we need to track when the type changes so we can create a new segment.

        it creates a clear separation between types of content,
        where all you ever need to do is create a new UI element when the segment type changes,
        without worrying about merging the different types of tokens manually

        this used to be exclusive to the webUI, handled in the frontend.
        but since this is now in the core, it can be used in *ANY* channel.

        usage: (from within your channel's run()):
          async for partial_turn in self.get_streaming_turns(
              self.send_stream("user's message") 
          ):
              do_whatever_with(partial_turn)

        the state machine works like this:
        - if the token type changes, we create a new segment and start filling it
        - if the token type stays the same, we keep appending to the current segment
        - for tool responses, we don't yield them as segments,
          instead we merge their responses back into the corresponding tool_calls segment
        """

        current_segment = None
        last_segment_type = None
        stream_response_map = {}
        last_tool_call_id = None
        last_tool_calls_segment = None

        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-1)
        # -- step tracking: reasoning/content runs and the tool calls they
        # -- lead to share one step number; the step increments when a new
        # -- segment starts after the current one already attached tools
        # -- (that step is then complete). consumers accumulate steps from
        # -- the active-step-only yields by grouping on the step field.
        step_num = 0
        step_has_tools = False

        async for raw_token in stream_generator:
            # copy the token so we don't mutate it
            token = dict(raw_token)

            # yield the raw token in case it needs to be processed 
            # (for things like user messages, API errors, etc)
            yield {"type": "token", "content": token}

            # skip grouping for non-display tokens
            if token.get("type") in ['prompt_progress', 'token_usage', 'timings', 'user_message']:
                continue

            # remove timing data from the token
            if token.get("timings"):
                token.pop("timings")

            segment_type = token.get("type")
            
            # merge tool call deltas and toolcalls into one type
            if segment_type in ['tool_call_delta', 'tool_calls']:
                segment_type = 'tool_calls'

            # determine whether this is a new tool response (different tool_call_id)
            # since tool responses can arrive for multiple different tools in sequence,
            # each needs its own response tracking
            is_new_tool_response = (
                segment_type == 'tool' and 
                last_tool_call_id != token.get("tool_call_id")
            )

            # the grouping works like this:
            # if the token type is different from the previous one,
            # or if we're switching to a new tool response (different tool_call_id),
            # we create a new segment.
            #
            # otherwise, we append to the existing segment that's currently
            # being filled
            if segment_type != last_segment_type or is_new_tool_response:
                # create a new segment (message within the turn)
                current_segment = token.copy()
                current_segment["role"] = "assistant" if segment_type != 'tool' else "tool"
                current_segment["type"] = segment_type

                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # step bookkeeping: a new assistant segment starts a new
                # step only if the current one already attached tools (or
                # no step exists yet); tool calls themselves join the
                # reasoning run that preceded them
                if segment_type != 'tool':
                    if step_num == 0 or step_has_tools:
                        step_num += 1
                        step_has_tools = False
                    if segment_type == 'tool_calls':
                        step_has_tools = True
                    current_segment["step"] = step_num
                
                if segment_type == 'reasoning':
                    if "content" in current_segment.keys():
                        # remove non-reasoning content from the reasoning segment
                        current_segment.pop("content")

                    current_segment.setdefault("reasoning_content", token.get("content", ''))
                elif segment_type == 'content':
                    current_segment.setdefault("content", token.get("content", ''))
                elif segment_type == 'tool_calls':
                    # copy the list since we mutate it in place during merges
                    current_segment.setdefault("tool_calls", list(token.get("tool_calls", [])))
                    last_tool_calls_segment = current_segment  # remember this for later merging
                elif segment_type == 'tool':
                    current_segment["type"] = "tool_response"
                    current_segment.setdefault("content", token.get("content", ''))
                
                last_segment_type = segment_type
                last_tool_call_id = token.get("tool_call_id") if segment_type == 'tool' else None
            
            else:
                # if it's the same token type as the last one,
                # that means we're still working with the same segment,
                # so here's where we do the streaming magic
                # that merges new tokens into the existing segment
                if segment_type == 'tool_calls':
                    if token.get("tool_calls"):
                        existing_calls = current_segment.setdefault("tool_calls", [])
                        # merge the tool calls using their id
                        # so that batched tool calls properly show up
                        for incoming_call in token["tool_calls"]:
                            call_id = incoming_call.get("id")
                            if call_id:
                                for idx, existing_call in enumerate(existing_calls):
                                    if existing_call.get("id") == call_id:
                                        existing_calls[idx] = incoming_call
                                        break
                                else:
                                    existing_calls.append(incoming_call)
                            elif existing_calls and not existing_calls[-1].get("id"):
                                # no id to match on: assume it continues the last
                                # id-less call (providers that stream ids late/never)
                                existing_calls[-1] = incoming_call
                            else:
                                existing_calls.append(incoming_call)
                elif segment_type == 'tool':
                    current_segment["content"] = (current_segment.get("content") or '') + (token.get("content") or '')
                else:
                    content_key = "reasoning_content" if segment_type == 'reasoning' else 'content'
                    current_segment[content_key] = (current_segment.get(content_key) or '') + (token.get("content") or '')

            # tool responses need to be merged back into their corresponding tool calls
            # so we maintain a response map that accumulates tool response content by tool_call_id
            if token.get("type") == 'tool':
                stream_response_map[token["tool_call_id"]] = token.get("content", '')

            # ----
            # yield logic:
            # - for normal segments (reasoning, content, tool_calls), yield the current segment
            #   with any available tool responses merged into the tool calls
            # - for tool_response segments, we don't yield them directly. instead,
            #   we update the last_tool_calls_segment with the new response and re-yield it.
            # ----
            if current_segment.get("type") != 'tool_response':
                # merge tool responses into tool calls for display
                if current_segment.get("tool_calls"):
                    for tool in current_segment["tool_calls"]:
                        if tool.get("id") in stream_response_map:
                            tool["response"] = stream_response_map[tool["id"]]
                            # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                            # precomputed failed flag (mirrors group_history)
                            tool["failed"] = self._tool_call_failed(tool)
                        # arg summary (mirrors group_history)
                        tool["summary"] = self._tool_call_summary(tool)
                    # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                    # live step status + precomputed module display data
                    current_segment["step_status"] = self._step_status(current_segment["tool_calls"])
                    current_segment["modules"] = self._modules_for(current_segment["tool_calls"])
                else:
                    current_segment["step_status"] = "thinking"
                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # stamp the collapsed-header label, and skip yielding
                # segments with nothing visible: they'd be ghost stations
                current_segment["label"] = self._segment_label(current_segment)
                if self._has_visible_chain_content(current_segment):
                    yield {"type": "turn", "content": current_segment}
            elif last_tool_calls_segment:
                # tool response segment: update and re-yield the tool_calls segment instead
                for tool in last_tool_calls_segment["tool_calls"]:
                    if tool.get("id") in stream_response_map:
                        tool["response"] = stream_response_map[tool["id"]]
                        # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                        tool["failed"] = self._tool_call_failed(tool)
                    tool["summary"] = self._tool_call_summary(tool)
                # -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
                # responses landed: refresh the re-yielded step's status
                last_tool_calls_segment["step_status"] = self._step_status(last_tool_calls_segment["tool_calls"])
                last_tool_calls_segment["label"] = self._segment_label(last_tool_calls_segment)
                yield {"type": "turn", "content": last_tool_calls_segment}

