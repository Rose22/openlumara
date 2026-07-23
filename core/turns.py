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

    def group_history(self, history):
        """
        Groups all finalized messages from history into turns.
        Returns a list of turn objects.
        """
        turns = []
        current_assistant_turn = None

        for msg in history:
            role = msg.get('role')
            
            if role == 'user':
                if current_assistant_turn:
                    # if a user message arrives and it's currently still
                    # the assistant's turn, that means we finalize it, and move onto a new turn!
                    turns.append(current_assistant_turn)
                    current_assistant_turn = None
                
                # append the user message as a single turn. a user message is never multiple turns
                turns.append({
                    "role": "user",
                    "messages": [msg.copy()]
                })
            else:
                # create the assistant turn if it doesn't already exist
                if not current_assistant_turn:
                    current_assistant_turn = {
                        "role": "assistant",
                        "index": msg.get("index"),
                        "messages": []
                    }
                    
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
                            
        return turns

    async def group_stream(self, stream_generator):
        """
        Processes the stream generator and yields the 'streaming turn' object
        as it is built up.
        """
        segments = []
        last_segment_type = None
        stream_response_map = {}

        # i've put comments all over this function in order to help me and others better understand what's going on here
        # since this is quite complex, but essential to what makes openlumara's UX nice

        # this is basically a state machine that groups tokens
        
        # throughout this function you'll see mentions of "segments"
        # a segment is basically a group of tokens that are of the same type

        # since we can have multiple messages within a turn, for example
        # user -> assistant (reasoning+content) -> toolcalls -> tool response -> 
        # -> assistant (reasoning only) -> toolcalls -> tool response -> assistant final answer (reasoning+content)

        # it's essential that we don't group tokens of the same type into just *one* container for each type
        # instead, we have a list of groups, so that if for example some reasoning comes in,
        # we create a 'reasoning' segment and fill it with reasoning tokens,
        # then once it switches to content, we create a 'content' segment and fill that with content tokens
        # then once it calls a tool, create a tool segment,
        # then once it reasons again, **we create a new reasoning segment seperate from the previous one**

        # this way, we can display each segment throughout the UI, seperately,
        # using whatever layout and components we want!

        # this used to be exclusive to the webUI, and handled in the frontend.
        # but since this is now in the core, it can be used in *ANY* channel.

        # usage: (from within your channel's run()):
        #   async for partial_turn in self.get_streaming_turns(
        #       self.send_stream("user's message") 
        #   ):
        #       do_whatever_with(partial_turn)

        async for raw_token in stream_generator:
            # copy the token so we don't mutate it
            token = dict(raw_token)

            # yield the raw token in case it needs to be processed (for things like user messages, API errors, etc)
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

            # determine whether this is a new tool response
            last_msg = segments[-1] if segments else None
            is_new_tool_response = (
                segment_type == 'tool' and 
                (not last_msg or last_msg.get("tool_call_id") != token.get("tool_call_id"))
            )

            # the grouping works like this:
            # if the token type coming is is different from the previous one,
            # we create a new segment.
            #
            # otherwise, we merge it into the existing segment that's currently
            # being grouped
            if segment_type != last_segment_type or is_new_tool_response:
                # create a new segment (message within the turn)
                new_segment = token.copy()
                new_segment["role"] = "assistant" if segment_type != 'tool' else "tool"
                new_segment["type"] = segment_type
                
                if segment_type == 'reasoning':
                    if "content" in new_segment.keys():
                        # remove non-reasoning content from the reasoning segment
                        new_segment.pop("content")

                    new_segment.setdefault("reasoning_content", token.get("content", ''))
                elif segment_type == 'content':
                    new_segment.setdefault("content", token.get("content", ''))
                elif segment_type == 'tool_calls':
                    new_segment.setdefault("tool_calls", token.get("tool_calls", []))
                elif segment_type == 'tool':
                    new_segment["type"] = "tool_response"
                    new_segment.setdefault("content", token.get("content", ''))
                
                segments.append(new_segment)
                last_segment_type = segment_type
            
            else:
                # if it's the same token type as the last one,
                # that means we're still working with the same segment,
                # so here's where we do the streaming magic
                # that merges new tokens into existing segments
                if last_msg:
                    if segment_type == 'tool_calls':
                        if token.get("tool_calls"):
                            last_msg["tool_calls"] = token["tool_calls"]
                    elif segment_type == 'tool':
                        last_msg["content"] = (last_msg.get("content") or '') + (token.get("content") or '')
                    else:
                        content_key = "reasoning_content" if segment_type == 'reasoning' else "content"
                        last_msg[content_key] = (last_msg.get(content_key) or '') + (token.get("content") or '')

            # -----
            # the part that merges tool responses into the toolcalls
            # -----
            # Build response map for merging
            if token.get("type") == 'tool':
                stream_response_map[token["tool_call_id"]] = token.get("content", '')

            # Filter and merge for display
            display_segments = [s for s in segments if s.get("type") != 'tool_response']
            
            for msg in display_segments:
                if msg.get("tool_calls"):
                    for tool in msg["tool_calls"]:
                        if tool.get("id") in stream_response_map:
                            tool["response"] = stream_response_map[tool["id"]]

            # collect it all into one turn object that dynamically updates as tokens come in
            streaming_turn = {
                "role": "assistant",
                "messages": display_segments
            }

            # aaand yield!
            yield {"type": "turn", "content": streaming_turn}
