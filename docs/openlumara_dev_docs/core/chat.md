# Core: The Chat System (`core.Chat`)

The `Chat` class is responsible for managing the lifecycle and persistence of individual chat sessions. It acts as the interface between the high-level `Context` and the low-level persistent storage.

## Responsibilities

### 1. Session Management
`Chat` manages a collection of chat sessions, allowing the user to:
- **Create New Chats**: Start fresh conversations with unique IDs and metadata.
- **Switch Chats**: Load existing chat histories by their ID.
- **Clear Chats**: Wipe the message history of the current session.
- **Delete Chats**: Permanently remove a chat session from storage.
- **Auto-Resume**: Automatically reload the last used chat session upon application startup.

### 2. Message Persistence
Every message sent or received is stored within a chat session. `Chat` ensures that:
- **History is Maintained**: The sequence of user and assistant messages is preserved.
- **Metadata is Stored**: Titles, categories, tags, and custom metadata (like character info) are kept alongside the messages.
- **Efficient Storage**: Data is saved using efficient formats (like JSON) to ensure fast loading and low overhead.

### 3. Token Tracking
`Chat` tracks the token usage of the current conversation:
- **API-Provided Usage**: Whenever the API returns usage data, `Chat` updates its internal counter.
- **Local Estimation**: If the API does not provide usage data, `Chat` uses a local tokenizer (`tiktoken`) to estimate the number of tokens used in the current context.

### 4. Data Integrity and Cleanup
`Chat` performs maintenance on the chat collection:
- **Automatic Title Generation**: When a new message is sent in a blank chat, it automatically generates a short title based on the message content.
- **Cleanup**: Automatically removes "empty" chats (chats with no messages) or chats that only contain system commands.

## Key Methods

| Method | Description |
| :--- | :--- |
| `new(category, title, metadata)` | Creates a new chat session. |
| `clear()` | Deletes all messages from the current chat. |
| `delete(id)` | Permanently removes a chat session by its ID. |
| `load(id)` | Loads an existing chat session into the current context. |
| `get()` | Retrieves the full list of messages in the current chat. |
| `add(message, ghost=False)` | Appends a new message to the current chat history. |
| `pop(index)` | Removes a specific message from the history. |
| `count_tokens(messages)` | Calculates the estimated token count of a list of messages. |
| `set_data(key, value)` | Stores custom metadata within the current chat session. |

## Data Structure

A single chat session is represented as a dictionary:

```json
{
  "id": "8-char-ulid",
  "title": "Chat Title",
  "category": "general",
  "tags": ["tag1", "tag2"],
  "messages": [
    {"role": "user", "content": "Hello!"},
    {"role": "assistant", "content": "Hi there!"}
  ],
  "custom_data": {
    "character": "some_char_id"
  },
  "created": "ISO-timestamp",
  "updated": "ISO-timestamp",
  "token_usage": 1234
}
```
