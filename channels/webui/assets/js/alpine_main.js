// alpine data used in the main container over in templates/index.html
document.addEventListener('alpine:init', () => {
    Alpine.data('main', () => ({
        chats: [],
        categories: [],
        chat: {},
        messages: [],
        user_input: '',
        selectedChat: null,
        selectedCategory: 'general',

        async init() {
            // fetch current chat
            this.chat = await simpleApiFetch('/api/chat/current');
            if (this.chat) {
                this.selectedChat = this.chat.id;
                this.messages = this.chat.messages;
            }

            // fetch all other data
            this.chats = await simpleApiFetch('/api/chats');
            this.categories = await simpleApiFetch('/api/chats/categories');

            await connectWebSocket();
        },

        async selectChat(chatId) {
            if (this.selectedChat === chatId) { return; }

            this.chat = await simpleApiFetch(`/api/chat/load/${chatId}`);
            this.selectedChat = this.chat.id;
            this.messages = this.chat.messages;
        },

        async newChat() {
            await simpleApiPost('/api/chat/new');

            this.chat = await simpleApiFetch('/api/chat/current');
            this.selectedChat = this.chat.id;

            await this.reloadChats();
            await this.reloadChat();
        },

        async reloadChat() {
            if (Alpine.store("stream").state === "streaming") {
                // block chat reload during streaming
                return;
            }

            if (!this.selectedChat) {
                console.log("tried to reload the chat, but no chat is loaded!");
                return;
            }

            this.chat = await simpleApiFetch(`/api/chat/load/${this.selectedChat}`);
            this.messages = this.chat.messages;
        },

        async reloadChats() {
            this.chats = await simpleApiFetch('/api/chats');
        },

        async selectCategory(category) {
            this.selectedCategory = category;
        },

        get promptprogress() {
            // does the math for the prompt processing indicator over in components/promptprocess.html
            // the math was ported straight over from the old webUI because, well, it works, and it's clean code
            const progressData = Alpine.store("stream").processing;

            const cache = progressData.cache || 0;
            const processed = progressData.processed - cache;
            const total = progressData.total - cache;
            const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
            const elapsed = progressData.time_ms / 1000;
            const remaining = (total - processed) > 0 ? (elapsed / processed) * (total - processed) : 0;

            return {
                cache,
                processed,
                total,
                percent,
                percent_str: `${percent}%`,
                elapsed: elapsed.toFixed(1),
                remaining,
                remaining_str: `(ETA: ${Math.ceil(remaining)}s)`
            };
        },

        get turns() {
            /*
             * this absolute black magic, ported over from the old webUI,
             * with help from my local AI (not vibecoded, but i needed help for this because this is really hard!),
             * emits an array of messages where every message
             * inbetween the latest user message,
             * is grouped into one assistant turn.
             *
             * this makes it display just like in the old webUI,
             * but using alpine's reactivity and none of the horrible DOM injection hackiness
             * that the AI decided to vibecode back then
             *
             * if anyone wants to know, i used Qwen3.6 35B for this, at Q6_K_M quant.
             * i barely use cloud AI anymore for coding help,
             * and in fact, when i use AI to help coding on openlumara,
             * i use openlumara itself for it :)
             */

            // 1. Group all finalized messages from history
            const turns = [];
            let currentAssistantTurn = null;

            for (const msg of this.messages) {
                if (msg.role === 'user') {
                    if (currentAssistantTurn) {
                        turns.push(currentAssistantTurn);
                        currentAssistantTurn = null;
                    }
                    turns.push({
                        role: "user",
                        messages: [{"role": "user", "content": msg.content}]
                    });
                } else {
                    if (!currentAssistantTurn) {
                        currentAssistantTurn = {
                            role: "assistant",
                            messages: []
                        };
                    }

                    // normalize historical messages to include a type property
                    // so that it works both when not streaming and when streaming
                    if (msg.tool_calls) {
                        msg.type = "tool_calls"
                    } else {
                        msg.type = 'history';
                    }
                    currentAssistantTurn.messages.push(msg);
                }
            }
            if (currentAssistantTurn) turns.push(currentAssistantTurn);

            // 2. Reconstruct streaming turn from token segments
            /*
             * this is the part that handles streaming tokens...
             * absolute black magic if you ask me
             */
            const stream = Alpine.store('stream');
            if (
                stream.state === 'streaming' || stream.state === 'calling_tools' || stream.state === 'processing_tools' 
                && stream.tokens
                && stream.tokens.length > 0
            ) {
                const segments = [];
                let lastSegmentType = null;

                for (const token of stream.tokens) {
                    // Skip non-display tokens
                    if (token.type === 'prompt_progress' || token.type === 'token_usage' || token.type === 'timings') {
                        continue;
                    }

                    // Skip tokens with no actual content (prevents blank segments)
                    if (token.type === 'reasoning' && (!token.content || token.content.trim() === '')) {
                        continue;
                    }

                    let segmentType = token.type;
                    // Normalize tool call types into a single segment type
                    // if (token.type === 'tool_call_delta' || token.type === 'tool_calls') {
                    //     segmentType = 'tool_calls';
                    // }

                    if (segmentType !== lastSegmentType) {
                        // New segment type: start a fresh message
                        if (segmentType === 'reasoning') {
                            segments.push({
                                role: "assistant",
                                type: "reasoning",
                                reasoning_content: token.content || '',
                                pending: true
                            });
                        } else if (segmentType === 'content') {
                            segments.push({
                                role: "assistant",
                                type: "content",
                                content: token.content || '',
                                pending: true
                            });
                        } else if (segmentType === 'tool_calls') {
                            segments.push({
                                role: "assistant",
                                type: "tool_calls",
                                tool_calls: token.tool_calls || [],
                                pending: true
                            });
                        } else if (segmentType === 'tool_call_delta') {
                            segments.push({
                                role: "assistant",
                                type: "tool_call_delta",
                                tool_calls: token.tool_calls || [],
                                pending: true
                            });
                        } else if (segmentType === 'tool') {
                            segments.push({
                                role: "tool",
                                type: "tool_response",
                                content: token.content || '',
                                tool_call_id: token.tool_call_id || '',
                                pending: true
                            });
                        }
                        
                        lastSegmentType = segmentType;
                    } else {
                        // Same segment type: append to the last message
                        const lastMsg = segments[segments.length - 1];
                        if (lastMsg) {
                            if (segmentType === 'tool_calls') {
                                // Merge tool calls (deltas build up, final token completes)
                                if (token.tool_calls) {
                                    lastMsg.tool_calls = lastMsg.tool_calls.concat(token.tool_calls);
                                }
                            } else {
                                if (segmentType === 'reasoning') {
                                    lastMsg.reasoning_content += (token.content || '');
                                } else {
                                    lastMsg.content += (token.content || '');
                                }
                            }
                        }
                    }
                }

                if (segments.length > 0) {
                    turns.push({
                        role: "assistant",
                        messages: segments
                    });
                }
            }

            return turns;

            /* 
             * you can really see the difference between my comments and the AI's, huh?
             * well good, i want to keep it that way, so that it's obvious which parts
             * have been tainted by AI, and which haven't
             */
        },
    }));

    // stores streaming-related data
    Alpine.store('stream', {
        // one of: idle, sending, processing, streaming
        state: 'idle',

        // stores raw token data
        tokens: [],
        processing: {},

        async clearTokens() {
            this.tokens = [];
            this.processing = [];
        }
    });

    Alpine.directive('auto-scroll', (el) => {
      let isAtBottom = true;

      const checkBottom = () => {
        const threshold = 50; // px tolerance
        isAtBottom = (el.scrollHeight - el.scrollTop - el.clientHeight) < threshold;
      };

      el.addEventListener('scroll', checkBottom);

      const observer = new MutationObserver(() => {
        if (isAtBottom) {
          el.scrollTop = el.scrollHeight;
        }
      });

      observer.observe(el, { childList: true, subtree: true });

      return () => {
        el.removeEventListener('scroll', checkBottom);
        observer.disconnect();
      };
    });
})
