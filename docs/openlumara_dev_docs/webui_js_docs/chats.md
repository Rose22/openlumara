# chats.js Documentation

`chats.js` manages the chat list, chat categorization, and the loading/unloading of individual chat sessions. It is highly optimized for performance, using a `Map` for $O(1)$ lookups and `IntersectionObserver` for lazy-loading chat items.

## Core Functionality

### Chat List Management
- `loadChats()`: Fetches all chats and tags from the backend.
  - Populates `allChats` and `allTags`.
  - Creates a `chatDataMap` for fast access.
  - Dynamically identifies categories (including metadata-driven ones like `char:Bob`).
  - Renders the category list and the chat list.
- `renderChatList(chats)`: Renders the chat list using a `DocumentFragment` to minimize reflows.
  - **Lazy Loading**: Uses `chatListObserver` (an `IntersectionObserver`) to only populate chat items with real data when they are about to enter the viewport.
- `populateChatItem(item, chat)`: Fills a chat item shell with its actual title, metadata, and action buttons.
- `createChatItemShell(chat)`: Creates a lightweight placeholder for a chat item to optimize initial load performance.

### Chat Loading & Navigation
- `loadChat(chatId)`: The primary function for switching to a new chat.
  - Loads the chat via `/chat/load`.
  - Updates the UI (title, tags, messages).
  - Handles category switching by re-running `loadChats()` if the category has changed.
- `restoreCurrentChat()`: Automatically loads the last active chat session on page load.
- `scrollToActiveChat()`: Ensures the selected chat is visible in the sidebar, even if it was lazy-loaded.

### Categorization & Metadata
- `selectCategory(categoryKey)`: Switches the active category and re-renders the chat list.
- `filterChatsByCategory(chats, categoryKey)`: Filters the chat array based on the selected category or metadata prefix (e.g., `char:`).
- `parseCategory(categoryString)`: Parses a category string into a structured object, handling both standard categories and metadata-driven groups.
- `moveChatToCategory(chatId, newCategory)`: Updates a chat's category via the backend and refreshes the list.

### Search & Filtering
- `filterChats(query)`: Performs a search across chat titles and (if enabled) message content.
- `filterTagsBySearch(query)`: Filters the visible tags based on the current search query.

## Optimizations
- **`chatDataMap`**: A `Map` that stores all chat objects, allowing immediate access to chat data without repeated JSON parsing or array searching.
- **IntersectionObserver**: Prevents the DOM from being overwhelmed by hundreds of complex chat elements by only rendering what is visible.
- **`DocumentFragment`**: Used during list rendering to batch DOM updates.
