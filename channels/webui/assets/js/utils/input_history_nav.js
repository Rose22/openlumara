// styles that affect where text wraps or how tall a line is. copying these
// onto the mirror div is what makes its line layout match the textarea's
const INPUT_HISTORY_MIRROR_PROPS = [
    'fontFamily', 'fontSize', 'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch',
    'lineHeight', 'letterSpacing', 'wordSpacing', 'textIndent', 'textRendering',
    'textTransform', 'whiteSpace', 'wordBreak', 'overflowWrap', 'tabSize',
    'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
    'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth'
];

/*
 * measure whether the caret can move to a visual line above/below itself.
 * a hidden mirror div holding the textarea's text is laid out at the same
 * content width, and three zero-width markers (start / caret / end) reveal
 * which wrapped line the caret sits on. wrapped lines count, not just
 * newlines, so a long single-paragraph message behaves terminal-accurate:
 * the arrows walk through its rows first, and only then touch history.
 */
function textareaCaretLineBounds(textarea) {
    const pos = textarea.selectionStart;
    const style = window.getComputedStyle(textarea);

    const mirror = document.createElement('div');
    for (const prop of INPUT_HISTORY_MIRROR_PROPS) {
        mirror.style[prop] = style[prop];
    }
    mirror.style.whiteSpace = 'pre-wrap';
    mirror.style.overflowWrap = 'break-word';
    mirror.style.boxSizing = 'border-box';
    mirror.style.position = 'fixed';
    mirror.style.top = '-9999px';
    mirror.style.left = '-9999px';
    mirror.style.visibility = 'hidden';
    mirror.style.overflow = 'hidden';
    // clientWidth excludes the scrollbar but includes padding, so adding
    // the borders back lands on the textarea's content width under border-box
    mirror.style.width = (textarea.clientWidth
        + parseFloat(style.borderLeftWidth || 0)
        + parseFloat(style.borderRightWidth || 0)) + 'px';

    // the zero-width spaces give each marker a layout box without
    // affecting wrapping; the trailing one keeps a final newline visible
    const zwsp = '\u200b';
    const startMark = document.createElement('span');
    const caretMark = document.createElement('span');
    const endMark = document.createElement('span');
    startMark.textContent = zwsp;
    caretMark.textContent = zwsp;
    endMark.textContent = zwsp;
    mirror.append(startMark, textarea.value.slice(0, pos), caretMark, textarea.value.slice(pos), endMark);

    document.body.appendChild(mirror);
    const first = startMark.offsetTop;
    const caret = caretMark.offsetTop;
    const last = endMark.offsetTop;
    mirror.remove();

    return {
        canMoveUp: caret > first,
        canMoveDown: caret < last
    };
}

/*
 * fire the autosize plugin (same event its $autosize magic dispatches) on
 * the next microtask, which lands after alpine has written the current
 * user_input value into the textarea.
 *
 * the transition shuffling matters: the input's CSS animates `all`, and the
 * autosize plugin measures scrollHeight synchronously right after clearing
 * the height. mid-transition the box is still at its old height, so
 * scrollHeight reports that old (taller) value and recalling a short message
 * over a long one would never shrink the box. killing the transition for the
 * synchronous resize sidesteps the lie, then it gets handed back.
 */
function autosizeAfterUpdate(textarea) {
    queueMicrotask(() => {
        const transition = textarea.style.transition;
        textarea.style.transition = 'none';
        textarea.dispatchEvent(new Event('autosize'));
        textarea.style.transition = transition;
    });
}

/*
 * keydown handler for plain up/down arrows on the chat input. returns true
 * when history was recalled (the browser's cursor move was prevented).
 * modified arrows (ctrl+up etc. keep their own bindings), IME composition
 * and any press where the cursor still has room to move are left alone.
 */
function inputHistoryNav(event, textarea, direction) {
    if (event.ctrlKey || event.altKey || event.metaKey || event.shiftKey || event.isComposing) {
        return false;
    }

    const chat = Alpine.store('chat');
    // nothing above to recall / nothing recalled to step back down from
    if (direction === 'up' ? !chat.inputHistory.length : chat.historyIndex === -1) {
        return false;
    }

    const bounds = textareaCaretLineBounds(textarea);
    if (direction === 'up' ? bounds.canMoveUp : bounds.canMoveDown) {
        return false; // cursor still has room; let it move normally
    }

    event.preventDefault();
    if (direction === 'up') {
        chat.historyPrev();
    } else {
        chat.historyNext();
    }

    // park the caret at the end of the recalled text like readline does,
    // once x-model has written it (next microtask), and resize the box
    queueMicrotask(() => {
        const len = textarea.value.length;
        textarea.setSelectionRange(len, len);
    });
    autosizeAfterUpdate(textarea);
    return true;
}
