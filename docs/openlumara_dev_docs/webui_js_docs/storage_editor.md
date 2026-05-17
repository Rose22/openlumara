# Documentation: `storage_editor.js`

## Overview
`storage_editor.js` provides a sophisticated interface for managing and editing files stored on the server. It supports different file types (dictionaries, lists, and plain text) and includes a powerful "JSON Drill-Down" navigator for exploring complex nested dictionary structures.

## Core Functionality

### File Management
- **`showStorageEditor()`**: Opens the storage management modal and initializes the file list.
- **`loadStorageFiles()`**: Fetches the list of available files from the `/storage/list` endpoint and renders them.
- **`loadStorageFile(filePath)`**: Loads the content and type of a specific file from `/storage/load`. It then triggers the appropriate editor based on the file type.
- **`saveStorageFile()`**: Sends the current state of the editor back to the server via `/storage/save`.
- **`discardStorageChanges()`**: Reverts the current editor to the last saved state from the server.
- **`showNewFilePrompt()`**: Allows users to create new files by providing a name and selecting a type (`dict`, `list`, or `text`).

### Editor Types

#### 1. Dictionary (Dict) Editor
Designed for JSON-like objects. It features a two-column drill-down system.
- **Key List**: A sidebar listing all top-level keys and their data types.
- **JSON Navigator**: A two-column view for navigating nested structures.
    - **Breadcrumb**: Shows the path from the root to the current level (e.g., `root › settings › user`).
    - **Tree Column**: Displays the keys/indices of the current level.
    - **Editor Column**: Provides context-aware editors for the selected item:
        - **String**: A multi-line textarea.
        - **Number**: A numeric input.
        - **Boolean**: A toggle between `true` and `false`.
        - **Complex (Object/Array)**: A button to "drill into" the next level.
- **`selectDictKey(key)`**: Switches the view to a specific key within the dictionary.

#### 2. List Editor
Designed for arrays of items.
- **Item List**: A vertical list of items where each item is editable.
- **Reordering**: Buttons to move items up or down within the list.
- **Type Awareness**: Automatically detects if list items are strings, numbers, or objects and provides appropriate input methods.
- **`addListItem()` / `deleteListItem(index)`**: Management of list elements.

#### 3. Text Editor
A simple interface for plain text files.
- **Textarea**: A standard multi-line text area for direct editing.

## Key UI Features

| Feature | Description |
| :--- | :--- |
| **Dirty Indicator** | A visual cue (`storage-dirty-indicator`) that appears when unsaved changes are detected in the editor. |
| **Type Badges** | Visual labels next to keys/items indicating their data type (e.g., `string`, `number`, `[5]`, `{10}`). |
| **JSON Drill-Down** | Allows users to navigate deep into nested JSON objects without losing context, using a breadcrumb and tree structure. |
| **Loading States** | Spinners and placeholders are used during file fetch and save operations to provide feedback. |

## Data Flow

1. **Fetch**: `fetch('/storage/list')` $\rightarrow$ `renderStorageFiles()`.
2. **Load**: `fetch('/storage/load?file=...')` $\rightarrow$ `renderDictEditor()` / `renderListEditor()` / `renderTextEditor()`.
3. **Edit**: Local state (`currentStorageData`) is updated via `oninput` or `onclick` events.
4. **Save**: `fetch('/storage/save', { method: 'POST', body: JSON.stringify(...) })`.

## Utility Functions
- **`getValueTypeInfo(value)`**: Analyzes a JS value to return a type label and CSS class for UI rendering.
- **`escapeHtml(str)`**: Sanitizes strings to prevent XSS when rendering keys and values in the DOM.
- **`getDataAtPath(path)` / `setDataAtPath(value, path)`**: Helper functions to traverse and modify the nested `currentStorageData` object using a path array.
