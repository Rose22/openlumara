"""
Unit tests for core.sanitize.sanitize_leaked_tool_tags.

Run directly (no third-party deps needed):

    python3 core/sanitize_test.py

The sanitizer is loaded straight from its file so the test doesn't drag in the
whole `core` package (and its runtime dependencies) just to exercise a pure
string function.
"""

import os
import unittest
import importlib.util

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "sanitize.py")
_spec = importlib.util.spec_from_file_location("_sanitize_under_test", _MODULE_PATH)
_sanitize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sanitize)
sanitize_leaked_tool_tags = _sanitize.sanitize_leaked_tool_tags


class SanitizeLeakedToolTagsTest(unittest.TestCase):
    def test_clean_text_unchanged(self):
        text = "Here is the answer to your question."
        self.assertEqual(sanitize_leaked_tool_tags(text), text)

    def test_clean_text_unchanged_with_tool_calls(self):
        text = "Let me look that up for you."
        self.assertEqual(
            sanitize_leaked_tool_tags(text, has_tool_calls=True), text
        )

    def test_text_plus_trailing_tool_call(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("Let me help.\n</tool_call>", has_tool_calls=True),
            "Let me help.",
        )

    def test_lone_gt_then_closer(self):
        # the exact observed vLLM leak: ">" delta followed by "\n</tool_call>"
        self.assertEqual(
            sanitize_leaked_tool_tags(">\n</tool_call>", has_tool_calls=True), ""
        )

    def test_double_closer(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("</tool_call>\n\n</tool_call>", has_tool_calls=True),
            "",
        )

    def test_dash_closer_residue(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("-</tool_call>>", has_tool_calls=True), ""
        )

    def test_function_residue(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("</function>", has_tool_calls=True), ""
        )
        self.assertEqual(
            sanitize_leaked_tool_tags("<function=web_search>", has_tool_calls=True), ""
        )

    def test_content_with_tool_calls_becomes_empty(self):
        # pure whitespace/residue collapses to "" when tool_calls are present
        self.assertEqual(
            sanitize_leaked_tool_tags("  \n  ", has_tool_calls=True), ""
        )
        self.assertEqual(
            sanitize_leaked_tool_tags(">", has_tool_calls=True), ""
        )

    def test_real_text_preserved(self):
        # real text before a leaked closer survives, with the tag stripped
        self.assertEqual(
            sanitize_leaked_tool_tags(
                "I'll search for that.</tool_call>", has_tool_calls=True
            ),
            "I'll search for that.",
        )

    def test_compounding_orphan_as_plain_content(self):
        # no tool_calls: content that is ONLY orphan tags is stripped
        self.assertEqual(sanitize_leaked_tool_tags("</tool_call>"), "")
        self.assertEqual(sanitize_leaked_tool_tags("\n</tool_call>\n"), "")

    def test_no_tool_calls_real_text_with_orphan_tag(self):
        # mixed real text + orphan tag: keep the text, drop only the tag token
        self.assertEqual(
            sanitize_leaked_tool_tags("Sure, done!</tool_call>"),
            "Sure, done!",
        )

    def test_lone_gt_without_tags_kept_when_no_tool_calls(self):
        # conservative: a bare ">" with no wrapper and no tool_calls is legit
        # (e.g. a markdown blockquote) and must not be dropped
        self.assertEqual(sanitize_leaked_tool_tags("> a quote"), "> a quote")

    def test_code_span_mentions_preserved(self):
        # legitimate mention of the tag inside backticks is preserved
        inline = "Close the block with `</tool_call>` when done."
        self.assertEqual(sanitize_leaked_tool_tags(inline), inline)
        fenced = "```xml\n<tool_call>...</tool_call>\n```"
        self.assertEqual(sanitize_leaked_tool_tags(fenced), fenced)

    def test_non_string_returned_unchanged(self):
        self.assertIsNone(sanitize_leaked_tool_tags(None))
        self.assertEqual(sanitize_leaked_tool_tags(""), "")

    def test_tag_before_text_stripped_text_kept(self):
        # a leaked opener that arrives before real reasoning text: drop tag, keep text
        self.assertEqual(
            sanitize_leaked_tool_tags("<tool_call> real answer here", has_tool_calls=True),
            "real answer here",
        )


    # false positives found in review: text that only looks like a wrapper tag
    def test_prose_function_tag_untouched(self):
        for text in [
            "wrap it in a <function> element",
            "use <function-list> here",
            "a<function(b)>c",
            "html <functional>",
        ]:
            self.assertEqual(sanitize_leaked_tool_tags(text), text)

    def test_user_requested_xml_untouched(self):
        text = 'Here is the XML:\n<function name="f">\n  <param/>\n</function>'
        self.assertEqual(sanitize_leaked_tool_tags(text), text)

    def test_legit_trailing_gt_kept(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("ok </tool_call> then x >"), "ok  then x >"
        )

    def test_qwen_function_opener_stripped(self):
        self.assertEqual(sanitize_leaked_tool_tags("hi\n<function=get_weather>"), "hi")

    def test_leaked_gt_line_before_closer_stripped(self):
        self.assertEqual(
            sanitize_leaked_tool_tags("Checking.\n>\n</tool_call>", has_tool_calls=True),
            "Checking.",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
