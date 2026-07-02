# Core: The Tool Call Manager (`core.ToolcallManager`)

The `ToolcallManager` is responsible for processing tool calls from the AI's response, executing the corresponding Python functions, handling errors and timeouts, and managing the recursive tool-calling loop.

## Instance Attributes

| Attribute | Type | Description |
| :--- | :--- | :--- |
| `channel` | `Channel` | Reference to the owning channel (for context and logging). |

## Responsibilities

### 1. Tool Call Parsing and Repair
- AI models sometimes return malformed JSON in tool call arguments. The manager uses `json_repair` to fix broken JSON before execution.
- Handles both dict and string argument formats.
- Validates that arguments are dictionaries; converts empty/invalid to `{}`.

### 2. Tool Resolution
- Scans all loaded modules to find the module that owns the requested tool.
- Matches tool names by prefix (e.g., `memory_add` → module `memory` → method `add`).
- Checks if the tool is disabled in the module's `disabled_tools` list.

### 3. Tool Execution
- Executes the tool function with the parsed arguments.
- Enforces a configurable timeout (`core.tool_timeout`, default 10s) via `asyncio.wait_for()`.
- Catches and handles `TimeoutError` and general exceptions, wrapping results in `module.result()` format.
- Logs tool calls and results via the channel's logging system.

### 4. Recursive Tool Calling
- After executing all tool calls in a batch, the manager sends the tool results back to the AI via `API.send_stream()` and waits for the next response.
- If the AI makes another tool call, the process repeats recursively.
- Tracks the agentic loop start index after each complete tool-calling chain.
- Handles cancellation gracefully (announces cancellation to the channel).

### 5. Display Formatting
- Formats tool calls for display to the user with truncated argument values and nice styling.

## Key Methods

### Display
| Method | Description |
| :--- | :--- |
| `display_call(tool_data)` | Formats a tool call into a user-friendly string: `🔧 func_name(arg1="val1", arg2="val2")`. Truncates values longer than 30 chars. Handles both dict and object tool data formats. |

### Repair
| Method | Description |
| :--- | :--- |
| `_repair_tool_calls(tool_calls)` | Repairs malformed JSON in tool call arguments. Iterates through tool calls, attempts `json_repair.loads()`, and re-serializes valid dicts. |
| `_repair_toolcall_token(token)` | Async wrapper that repairs tool calls within a token dict. |

### Request Building
| Method | Description |
| :--- | :--- |
| `_build_recursive_request(token, final_content, final_reasoning)` | Builds a new assistant message dict for recursive tool calling. Includes accumulated content, reasoning, and repaired tool calls. |

### Processing
| Method | Description |
| :--- | :--- |
| `process(assistant_message, push=False, recursion_counter=0)` | **Main method.** Async generator that processes tool calls from an API response. Yields tool result tokens for display. Handles: repair → execute → yield result → recursive AI call → repeat. Returns None if a tool returns None (abort chain). |

## Tool Execution Flow

1. **Repair**: Fix malformed JSON in tool call arguments.
2. **Add to Context**: The assistant message with tool calls is added to the chat history.
3. **Push** (if `push=True`): The tool call is pushed to the channel's push queue for display.
4. **For each tool call**:
   a. Find the owning module by name prefix.
   b. Check if the tool is disabled.
   c. Execute the function with `asyncio.wait_for()` and timeout.
   d. Handle errors/timeouts → wrap in `module.result()` format.
   e. Build the tool response dict and yield it for display.
   f. Add the tool response to the chat history.
5. **Recursive Loop**: Send tool results back to AI via `send_stream()`.
   - If AI returns more tool calls → recurse.
   - If AI returns content/reasoning → add to context, set `agentic_loop_start`, push if needed.
   - If cancelled → announce cancellation and return.
6. **Final Message**: After the last recursive call, add the final assistant message to context.

## Timeout Configuration

Tool execution timeout is configurable via `config.core.tool_timeout` (default: 10 seconds). If a tool exceeds this timeout, it returns an error message: `"Tool timed out after {timeout}s"`.

## Error Handling

| Error Type | Handling |
| :--- | :--- |
| `asyncio.TimeoutError` | Returns `module.result("Tool timed out after Xs", success=False)` |
| General Exception | Returns `module.result("Error while executing tool: {error}", success=False)` |
| Tool returns `None` | Aborts the tool-calling chain immediately |
| API cancellation | Announces cancellation and returns early |
