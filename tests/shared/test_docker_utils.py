"""Tests for shared Docker utilities."""

from shared.utils.docker import sanitize_container_name


class TestSanitizeContainerName:
    def test_passthrough_valid_name(self) -> None:
        assert sanitize_container_name("my-container") == "my-container"

    def test_replaces_special_characters(self) -> None:
        assert sanitize_container_name("my container!@#") == "my-container"

    def test_collapses_repeated_dashes(self) -> None:
        assert sanitize_container_name("a---b") == "a-b"

    def test_strips_leading_non_alnum(self) -> None:
        assert sanitize_container_name("---abc") == "abc"

    def test_strips_trailing_separators(self) -> None:
        assert sanitize_container_name("abc-_.") == "abc"

    def test_returns_none_for_empty_input(self) -> None:
        assert sanitize_container_name("") is None

    def test_returns_none_for_all_special_chars(self) -> None:
        assert sanitize_container_name("!!!") is None

    def test_truncates_to_maxlen(self) -> None:
        result = sanitize_container_name("a" * 200, maxlen=10)
        assert result is not None
        assert len(result) <= 10

    def test_strips_trailing_separators_after_truncation(self) -> None:
        # "abcde-fgh" truncated to 6 -> "abcde-" -> "abcde"
        result = sanitize_container_name("abcde-fgh", maxlen=6)
        assert result == "abcde"

    def test_no_maxlen_preserves_length(self) -> None:
        long_name = "a" * 500
        result = sanitize_container_name(long_name)
        assert result == long_name

    def test_dots_and_underscores_allowed(self) -> None:
        assert sanitize_container_name("my.container_v2") == "my.container_v2"
