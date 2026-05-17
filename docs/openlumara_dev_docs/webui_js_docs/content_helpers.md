# Documentation: `content_helpers.js`

## Overview
`content_helpers.js` provides utility functions for processing and rendering message content. It is designed to handle both simple text strings and complex multimodal content arrays (e.g., messages containing text, images, and file references).

## Primary Functions

### `extractTextContent(content)`
Converts a message content payload into a single, flattened string.
- **Input**: Can be a `string` or an `Array` of part objects.
- **Multimodal Support**: If an array is provided, it iterates through the parts:
    - `type: 'text'`: Returns the text.
    - `type: 'file'`: Returns a placeholder like `File: filename`.
    - `type: 'image_url'`: Returns a placeholder like `[Image]`.
- **Output**: A single string where parts are joined by newlines. This is primarily used for search indexing and metadata extraction.

### `renderContentBody(content)`
The primary function for converting message content into HTML for display in the chat UI.
- **Text Content**: If the content is a string, it uses `renderMarkdown()` to convert it to HTML.
- **Multimodal Content**: If the content is an array, it maps over the parts:
    - **Text Parts**: Checks for special patterns like `[File: filename]` or `[Image: filename]` to render file/image preview containers instead of raw text.
    - **Image Parts**: If an `image_url` part is found, it renders an `<img>` tag with the provided URL.
- **Output**: An HTML string ready to be injected into the DOM.

### `extractSnippet(content, query, maxLength)`
Generates a highlighted text snippet for search results.
- **Contextual Search**: Finds the location of the `query` within the `content`.
- **Padding**: Adds a specified number of characters (`maxLength`) before and after the match to provide context.
- **Word Boundary Adjustment**: Attempts to avoid cutting words in half by adjusting the start/end points to the nearest whitespace.
- **Highlighting**: Wraps the matching query in `<mark>` tags using a case-insensitive regex.
- **Output**: An HTML string containing the snippet with `<mark>` tags and `...` ellipses if the snippet is truncated.

## Key Features

### Multimodal Rendering
The module allows the UI to seamlessly mix text with visual elements. It recognizes specific string patterns used during the upload/sending process to display file icons and image previews directly within the message bubble.

### Search Snippets
The snippet extractor is optimized for search result lists, providing enough context to the user to understand why a specific chat matched their query, while ensuring the HTML remains safe via `escapeHtml`.
