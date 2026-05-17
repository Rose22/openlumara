# tags.js Documentation

`tags.js` manages the tagging system used to categorize chats. It handles the rendering of the tag filter, the tag dropdown, and the logic for filtering chats by tag.

## Key Functions

### Tag Loading & State
- `loadTags()`: Fetches all available tags from the `/chat/tags` endpoint and renders the tag filter.
- `initTagFilterState()`: Restores the user's preference for whether the tag filter section is collapsed from `localStorage`.
- `toggleTagFilterSection()`: Expands or collapses the tag list section and persists the state.

### Tag Filtering
- `toggleTagFilter(tag)`: Selects or deselects a tag.
  - If the same tag is clicked again, it clears the filter.
  - Calls `updateTagsForCategory()` and `filterChatsByTag()` to refresh the UI.
- `clearTagFilter()`: Resets the active tag filter.
- `filterChatsByTag()`: Filters the DOM elements of the chat list. It adds a `.hidden-by-tag` class to any chat that does not contain the active tag.
- `filterTagsBySearch(query)`: Filters the visible tag chips in the sidebar based on a search query. It also checks if any chat matching that tag exists.

### UI Rendering
- `renderTagFilter(tagsToRender)`: Renders the list of tag chips in the sidebar.
- `fitTagsToContainer(container)`: A sophisticated function that ensures tags fit within the sidebar width.
  - If tags overflow, it hides the excess and shows a `+N` overflow indicator.
  - It uses `requestAnimationFrame` for recursive, layout-aware adjustment.
- `renderTitleBarTags()`: Renders the tags associated with the currently active chat in the chat title bar.
- `renderFittedTags(container, tags, options)`: Renders tags in a container (like the title bar) with smart overflow handling and responsive sizing.

### Tag Management
- `updateCurrentTags(tags)`: Sends a POST request to `/chat/tags` to update the tags for the current chat.
