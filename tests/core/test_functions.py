# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/functions.py - path sandboxing and small helpers.

intent of the sandbox family (from the code comments and the security report
that produced sandbox_open/sandbox_listdir): NO path a user or AI requests may
ever escape its sandbox base, follow a symlink, or smuggle traversal through
encoding tricks. those are the properties tested here - security properties
get green tests, broken-but-safe error contracts get strict xfail tests.
"""

import os

import pytest

import core


# ---- remove_duplicates -------------------------------------------------

def test_remove_duplicates_preserves_order():
    assert core.remove_duplicates([3, 1, 3, 2, 1]) == [3, 1, 2]


def test_remove_duplicates_handles_unhashable_items():
    # membership is checked with `in`, so dicts/lists work too
    items = [{"a": 1}, {"a": 1}, {"b": 2}]
    assert core.remove_duplicates(items) == [{"a": 1}, {"b": 2}]


def test_remove_duplicates_empty():
    assert core.remove_duplicates([]) == []


# ---- validate_path_string ----------------------------------------------

def test_validate_strips_surrounding_separators():
    assert core.validate_path_string("/some/path/") == os.path.join("some", "path")


def test_validate_rejects_dotdot_traversal():
    with pytest.raises(ValueError):
        core.validate_path_string("../etc/passwd")
    with pytest.raises(ValueError):
        core.validate_path_string(os.path.join("a", "..", "b"))


def test_validate_rejects_null_bytes():
    with pytest.raises(ValueError):
        core.validate_path_string("safe\x00name.txt")


def test_validate_rejects_url_encoded_traversal():
    # single, double and triple encoding must all be caught (it decodes up to
    # 3 rounds before checking)
    for payload in ("%2e%2e/etc", "%252e%252e/etc", "%25252e%25252e/etc"):
        with pytest.raises(ValueError):
            core.validate_path_string(payload)


def test_validate_normalizes_slashes_after_decoding():
    # %5c is a backslash: on any platform it must come out as os.sep so a
    # windows-style join can't sneak through
    result = core.validate_path_string("a%5cb")
    assert "\\" not in result
    assert result == os.path.join("a", "b")


# ---- sandbox_path --------------------------------------------------------

def test_sandbox_path_without_request_returns_base(tmp_path):
    assert core.sandbox_path(str(tmp_path)) == str(tmp_path)


def test_sandbox_path_joins_relative(tmp_path):
    assert core.sandbox_path(str(tmp_path), "sub/file.txt") == str(tmp_path / "sub" / "file.txt")


def test_sandbox_path_strips_leading_separators(tmp_path):
    assert core.sandbox_path(str(tmp_path), "/file.txt") == str(tmp_path / "file.txt")


def test_sandbox_path_similar_prefix_stays_inside(tmp_path):
    # base_evil must resolve to a CHILD of base, not a sibling directory
    base = tmp_path / "base"
    base.mkdir()
    result = core.sandbox_path(str(base), "/base_evil/file.txt")
    assert result == str(base / "base_evil" / "file.txt")


def test_sandbox_path_blocks_traversal(tmp_path):
    with pytest.raises(ValueError):
        core.sandbox_path(str(tmp_path), "../escape.txt")


def test_sandbox_path_blocks_encoded_traversal(tmp_path):
    with pytest.raises(ValueError):
        core.sandbox_path(str(tmp_path), "%2e%2e/escape.txt")


def test_sandbox_path_blocks_symlinked_component(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)

    with pytest.raises(ValueError):
        core.sandbox_path(str(base), "link/file.txt")


def test_sandbox_path_blocks_symlinked_final_component(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("secret")
    (base / "file.txt").symlink_to(victim)

    with pytest.raises(ValueError):
        core.sandbox_path(str(base), "file.txt")


# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
# FINDING (2026-10-25): sandbox_path strips the leading separator BEFORE the
# "remove the base path from it in case the AI/user inserts it" comparison, so
# for any absolute base the prefix-strip and the `path == base_path` branch
# can never match. a request that embeds the absolute base path gets joined
# under the base (base + full-request-minus-leading-slash) instead of being
# resolved. SECURITY HOLDS (the realpath check still keeps the result inside
# the base - covered green below), but the forgiving intent is broken.
# See also sandbox_open, which handles this correctly via basename stripping.

def test_sandbox_path_absolute_base_prefix_stays_inside_base(tmp_path):
    # green security half of the finding: whatever the prefix-strip does, the
    # result must never leave the sandbox
    base = tmp_path / "base"
    base.mkdir()
    result = core.sandbox_path(str(base), str(base / "sub" / "f.txt"))
    assert result == str(base) or result.startswith(str(base) + os.sep)


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: leading separator is stripped before the base-prefix "
           "comparison, so requests embedding the absolute base get double-joined",
)
def test_sandbox_path_request_with_absolute_base_resolves(tmp_path):
    # intent (code comment): "remove the base path from it in case the
    # AI/user inserts it"
    base = tmp_path / "base"
    base.mkdir()
    assert core.sandbox_path(str(base), str(base / "file.txt")) == str(base / "file.txt")


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: `path == base_path` branch is dead for absolute bases "
           "(leading separator stripped before comparison)",
)
def test_sandbox_path_equal_to_base_returns_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    assert core.sandbox_path(str(base), str(base)) == str(base)


# ---- sandbox_open (TOCTOU-safe open) -------------------------------------

def test_sandbox_open_read_write_roundtrip(tmp_path):
    fd = core.sandbox_open(str(tmp_path), "note.txt", os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    with os.fdopen(fd, "w") as f:
        f.write("hello")

    fd = core.sandbox_open(str(tmp_path), "note.txt", os.O_RDONLY)
    with os.fdopen(fd, "r") as f:
        assert f.read() == "hello"


def test_sandbox_open_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        core.sandbox_open(str(tmp_path), "../outside.txt", os.O_RDONLY)


def test_sandbox_open_rejects_opening_the_base_itself(tmp_path):
    with pytest.raises(ValueError):
        core.sandbox_open(str(tmp_path), "", os.O_RDONLY)


def test_sandbox_open_rejects_symlinked_target(tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("secret")
    (tmp_path / "link.txt").symlink_to(victim)

    with pytest.raises(ValueError):
        core.sandbox_open(str(tmp_path), "link.txt", os.O_RDONLY)


def test_sandbox_open_still_rejects_symlinked_directory_component(tmp_path):
    # green security half: the open MUST be refused, whatever the error type
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside)

    with pytest.raises(OSError):
        core.sandbox_open(str(tmp_path), "link/file.txt", os.O_RDONLY)


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: only ELOOP is translated to ValueError, but opening a "
           "symlinked DIRECTORY with O_NOFOLLOW|O_DIRECTORY raises ENOTDIR on linux, "
           "which leaks as a raw NotADirectoryError instead of ValueError",
)
def test_sandbox_open_symlinked_directory_component_raises_valueerror(tmp_path):
    # intent: every rejection path in this API raises ValueError
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside)

    with pytest.raises(ValueError):
        core.sandbox_open(str(tmp_path), "link/file.txt", os.O_RDONLY)


def test_sandbox_open_base_may_be_a_symlink(tmp_path):
    # intent (code comment): the sandbox base is operator-configured, so
    # opening IT through a symlink is allowed on purpose
    real = tmp_path / "real"
    real.mkdir()
    (real / "f.txt").write_text("ok")
    linked = tmp_path / "linked"
    linked.symlink_to(real)

    fd = core.sandbox_open(str(linked), "f.txt", os.O_RDONLY)
    with os.fdopen(fd, "r") as f:
        assert f.read() == "ok"


# ---- sandbox_listdir ------------------------------------------------------
# note: each test uses a dedicated subdir as base, since tmp_path itself
# holds the conftest's isolated config.yml / data dir.

def test_sandbox_listdir_lists_base(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "a.txt").touch()
    (base / "b").mkdir()
    assert sorted(core.sandbox_listdir(str(base))) == ["a.txt", "b"]


def test_sandbox_listdir_accepts_base_name_as_path(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    (base / "a.txt").touch()
    assert core.sandbox_listdir(str(base), "base") == ["a.txt"]


def test_sandbox_listdir_rejects_traversal(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(ValueError):
        core.sandbox_listdir(str(base), "..")


def test_sandbox_listdir_rejects_symlinked_directory(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)

    # green security half: the listing MUST be refused
    with pytest.raises(OSError):
        core.sandbox_listdir(str(base), "link")


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: same ENOTDIR-vs-ELOOP leak as sandbox_open - "
           "symlinked dir component should raise ValueError",
)
def test_sandbox_listdir_symlinked_directory_raises_valueerror(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (base / "link").symlink_to(outside)

    with pytest.raises(ValueError):
        core.sandbox_listdir(str(base), "link")


# ---- get_path --------------------------------------------------------------

def test_get_path_without_args_returns_project_root():
    assert core.get_path() == os.path.abspath(
        os.path.join(os.path.dirname(core.__file__), os.pardir)
    )


def test_get_path_passes_absolute_through():
    # intent: absolute paths come from trusted internal callers (e.g. a
    # configured absolute data folder) and are returned unchanged
    assert core.get_path("/some/absolute/path") == "/some/absolute/path"


def test_get_path_joins_relative_without_sandbox():
    result = core.get_path(os.path.join("..", "sibling"), sandbox=False)
    assert result.endswith(os.path.join("..", "sibling"))


def test_get_path_rejects_traversal_when_sandboxed():
    with pytest.raises(ValueError):
        core.get_path("../escape")


# ---- detail_error -----------------------------------------------------------

def test_detail_error_compact_when_debug_off(monkeypatch):
    monkeypatch.setattr(core, "debug", False)
    assert core.detail_error(ValueError("boom")) == "boom"


def test_detail_error_verbose_when_debug_on(monkeypatch):
    monkeypatch.setattr(core, "debug", True)
    try:
        raise ValueError("boom")
    except ValueError as e:
        detailed = core.detail_error(e)
    assert "boom" in detailed
    assert "test_functions.py" in detailed
    assert "ln:" in detailed
