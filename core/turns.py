import asyncio

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
            # copy the message so we never mutate the stored history:
            # the original code added 'index' / 'response' keys straight onto
            # the live message objects, which then leaked into saved history
            # files and into the tool_calls sent to the API
            msg = dict(msg)

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
                    "messages": [msg],
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

                # tool_calls are nested objects shared with the stored history,
                # so copy them too before we merge responses into them
                if msg.get("tool_calls"):
                    msg["tool_calls"] = [dict(tc) for tc in msg["tool_calls"]]

                current_assistant_turn["messages"].append(msg)

        if current_assistant_turn:
            turns.append(current_assistant_turn)

        # merge tool responses into their tool calls
        for turn in turns:
            if turn["role"] != 'assistant':
                continue
            
            response_map = {}
            for msg in turn["messages"]:
                if msg.get("role") == 'tool' and msg.get("tool_call_id"):
                    response_map[msg["tool_call_id"]] = msg.get("content")

            for msg in turn["messages"]:
                if msg.get("tool_calls"):
                    for tool in msg["tool_calls"]:
                        if tool.get("id") in response_map:
                            tool["response"] = response_map[tool["id"]]
                            
        return turns

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
                
                if segment_type == 'reasoning':
                    if "content" in current_segment.keys():
                        # remove non-reasoning content from the reasoning segment
                        current_segment.pop("content")

                    current_segment.setdefault("reasoning_content", token.get("content", ''))
                elif segment_type == 'content':
                    current_segment.setdefault("content", token.get("content", ''))
                elif segment_type == 'tool_calls':
                    current_segment.setdefault("tool_calls", token.get("tool_calls", []))
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
                        current_segment["tool_calls"] = token["tool_calls"]
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
                yield {"type": "turn", "content": current_segment}
            elif last_tool_calls_segment:
                # tool response segment: update and re-yield the tool_calls segment instead
                for tool in last_tool_calls_segment["tool_calls"]:
                    if tool.get("id") in stream_response_map:
                        tool["response"] = stream_response_map[tool["id"]]
                yield {"type": "turn", "content": last_tool_calls_segment}

