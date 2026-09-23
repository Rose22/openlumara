"""
Sanitize leaked tool-call wrapper fragments out of assistant content.

Some inference servers (notably vLLM's streaming `qwen3_coder` tool-call parser)
occasionally leak the tool-call closing wrapper into `content` deltas *after* the
structured `tool_calls` deltas have already been emitted, e.g. a `content: ">"`
delta followed by `content: "\n</tool_call>"`, with `finish_reason: "tool_calls"`.
The structured tool_calls themselves are correct.

If we persist that leaked trailing content into the assistant history message (or
render it to the user), the model imitates the orphan closers on later turns and
the problem compounds. This module strips those wrapper fragments while leaving
any legitimate text the model actually wrote untouched.

This is a pure function with no dependency on the rest of `core`, so it can be
imported and unit-tested in isolation.

Decision on code spans: tool-call tags that appear inside inline code (`...`) or
fenced code blocks (```...```) are preserved. If the model legitimately writes
about `</tool_call>` inside backticks we must not mangle it. Leaks always arrive
as bare, un-fenced fragments, so this is a safe way to tell them apart.
"""

import re

# The exact wrapper tokens qwen3's tool-call format uses, with optional leading "-"
# and one-or-more trailing ">" (handles the observed "-</tool_call>>" residue).
# Matches: <tool_call>  </tool_call>  <function=name>
# Deliberately narrow so prose/html like <function>, <function-list> or
# a<function(b)>c is left alone.
_WRAPPER_RE = re.compile(r"-?(?:</?tool_call>|<function=[^<>\s]*>)>*")

# </function> is also a real xml/html closer, so it's only stripped when the text
# has no matching <function ...> opener (i.e. it's an orphan)
_FUNCTION_CLOSE_RE = re.compile(r"-?</function>>*")
_FUNCTION_OPEN_RE = re.compile(r"<function[\s>]")

# the leak itself only ever contains closers. a plain reply that has an opener
# (<tool_call> or <function=...>) is the model writing out the format on purpose
_OPENER_RE = re.compile(r"<tool_call>|<function=[^<>\s]*>")

# Fenced code blocks first (so their inner backticks don't confuse the inline pass),
# then inline code spans.
_FENCED_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_RE = re.compile(r"`[^`]*`")

_PLACEHOLDER = "\x00CODESPAN{}\x00"


def _mask_code(text):
    """Replace code spans with opaque placeholders so we never touch their insides."""
    spans = []

    def _stash(match):
        spans.append(match.group(0))
        return _PLACEHOLDER.format(len(spans) - 1)

    text = _FENCED_RE.sub(_stash, text)
    text = _INLINE_RE.sub(_stash, text)
    return text, spans


def _unmask_code(text, spans):
    for index, original in enumerate(spans):
        text = text.replace(_PLACEHOLDER.format(index), original)
    return text


def _strip_trailing_gt_lines(text):
    """drop trailing lines holding nothing but ">" (the lone ">" delta that leaks before the closer)"""
    # done line by line: a regex like (\n[ \t]*>+[ \t]*)+$ backtracks quadratically on long runs of ">" lines
    lines = text.split("\n")
    while len(lines) > 1 and set(lines[-1].strip(" \t\r")) == {">"}:
        lines.pop()
    return "\n".join(lines)


def _is_only_residue(text):
    """True if what's left is nothing but whitespace and stray ">" leak residue."""
    stripped = text.strip()
    return stripped == "" or set(stripped) <= {">"}


def sanitize_leaked_tool_tags(content, has_tool_calls=False):
    """
    Strip leaked tool-call wrapper fragments from an assistant `content` string.

    - Removes complete orphan wrapper tokens (`</tool_call>`, `<tool_call>`,
      `<function=...>`, plus "-...>>" residue) that appear as bare text outside
      of code spans. `</function>` is only removed when no `<function ...>`
      opener is present, so real xml keeps its closer.
    - Without `has_tool_calls`, content containing an opener (`<tool_call>` or
      `<function=...>`) is returned unchanged: leaks are closers only, so an
      opener on a plain reply means the model is quoting the format.
    - If, after removal, nothing but whitespace / stray ">" residue remains, the
      content collapses to "".
    - When `has_tool_calls` is True, content that is *only* whitespace/">" residue
      is also collapsed to "" even if no wrapper token was present (the lone ">"
      that leaks as its own delta right before the closer).
    - Real text the model wrote is preserved. Content with no wrapper fragments is
      returned completely unchanged, so clean output is never altered.

    Returns the sanitized string. Non-string input is returned untouched.
    """
    if not isinstance(content, str) or content == "":
        return content

    masked, spans = _mask_code(content)

    # on a plain reply, an opener means the model is writing the tool-call format
    # on purpose (e.g. the user asked what it looks like), so leave it alone
    if not has_tool_calls and _OPENER_RE.search(masked):
        return content

    stripped_masked = _WRAPPER_RE.sub("", masked)
    if not _FUNCTION_OPEN_RE.search(stripped_masked):
        stripped_masked = _FUNCTION_CLOSE_RE.sub("", stripped_masked)
    removed_any = stripped_masked != masked
    only_residue = _is_only_residue(stripped_masked)

    # Pure-leak content collapses to empty.
    if only_residue and (removed_any or has_tool_calls):
        return ""

    # Nothing was a wrapper token: leave the model's real text exactly as-is.
    if not removed_any:
        return content

    # Real text survived alongside removed wrapper token(s): keep it, but trim
    # surrounding whitespace and any trailing ">"-only lines left behind.
    # a ">" that ends a line of real text (e.g. "x >") is kept.
    result = _unmask_code(stripped_masked, spans)
    result = _strip_trailing_gt_lines(result.strip())
    return result.strip()
