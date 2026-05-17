# utils.js Documentation

`utils.js` provides essential utility functions for managing UI interactions, scrolling, and input handling.

## Key Functions

### Scrolling Management
- `isScrolledToBottom()`: Checks if the user is within 50px of the bottom of the chat container.
- `scrollToBottom()`: Uses `requestAnimationFrame` to smoothly scroll the chat to the bottom, but only if `autoScrollEnabled` is true.
- `scrollToBottomDelayed()`: A delayed version of `scrollToBottom` using `setTimeout`.

### UI Utilities
- `formatTime()`: Returns a localized time string (HH:MM).
- `autoResize(textarea)`: Dynamically adjusts the height of a textarea (like the message input) based on its content, with a maximum height of 200px.
- `clearInput()`: Resets the message input field and resets its height via `autoResize`.

## Global State Variables
- `autoScrollEnabled`: A boolean that tracks whether the UI should automatically scroll to new messages. It is automatically set to `false` if the user scrolls up manually, allowing them to read history without being jumped to the bottom.
