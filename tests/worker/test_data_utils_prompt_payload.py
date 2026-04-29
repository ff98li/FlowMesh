"""Tests for `normalize_prompt_payload` in `data_utils`. Covers the
list-of-strings passthrough and the chat-style list-of-message-arrays
validation/normalization.
"""

import pytest

from worker.executors.base_executor import ExecutionError
from worker.executors.utils.data_utils import normalize_prompt_payload

# ---- Empty / strings passthrough --------------------------------------


def test_empty_list_returns_empty() -> None:
    prompts, apply_template, system = normalize_prompt_payload([])
    assert prompts == []
    assert apply_template is False
    assert system is False


def test_list_of_strings_passes_through() -> None:
    items = ["hello", "world"]
    prompts, apply_template, system = normalize_prompt_payload(items)
    assert prompts == items
    assert apply_template is False
    assert system is False


# ---- Message-array happy paths ----------------------------------------


def test_user_only_item() -> None:
    items = [[{"role": "user", "content": "hi"}]]
    prompts, apply_template, system = normalize_prompt_payload(items)
    assert prompts == [[{"role": "user", "content": "hi"}]]
    assert apply_template is True
    assert system is False


def test_system_plus_user_item() -> None:
    items = [
        [
            {"role": "system", "content": "You are terse."},
            {"role": "user", "content": "hi"},
        ]
    ]
    prompts, apply_template, system = normalize_prompt_payload(items)
    assert prompts == items
    assert apply_template is True
    assert system is True


def test_multi_turn_history_preserved() -> None:
    items = [
        [
            {"role": "system", "content": "ctx"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ]
    ]
    prompts, _, system = normalize_prompt_payload(items)
    assert prompts == items
    assert system is True


def test_extra_message_fields_are_dropped() -> None:
    items = [[{"role": "user", "content": "hi", "name": "alice", "extra": 1}]]
    prompts, _, _ = normalize_prompt_payload(items)
    assert prompts == [[{"role": "user", "content": "hi"}]]


def test_multiple_items_consistent_with_system() -> None:
    items = [
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "a"},
        ],
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "b"},
        ],
    ]
    prompts, _, system = normalize_prompt_payload(items)
    assert prompts == items
    assert system is True


def test_multiple_items_consistent_without_system() -> None:
    items = [
        [{"role": "user", "content": "a"}],
        [{"role": "user", "content": "b"}],
    ]
    prompts, _, system = normalize_prompt_payload(items)
    assert prompts == items
    assert system is False


# ---- Heterogeneous top-level items ------------------------------------


def test_mixed_str_and_list_rejected() -> None:
    with pytest.raises(ExecutionError, match="homogeneous"):
        normalize_prompt_payload(["s", [{"role": "user", "content": "x"}]])


def test_mixed_list_and_str_rejected() -> None:
    with pytest.raises(ExecutionError, match="homogeneous"):
        normalize_prompt_payload([[{"role": "user", "content": "x"}], "s"])


def test_unsupported_top_level_item_type_rejected() -> None:
    """Top-level items that are neither str nor list (e.g. dict) are rejected."""
    with pytest.raises(ExecutionError, match="homogeneous"):
        normalize_prompt_payload([{"role": "user", "content": "x"}])


# ---- Per-item validation ----------------------------------------------


def test_empty_message_list_rejected() -> None:
    with pytest.raises(ExecutionError, match="non-empty list"):
        normalize_prompt_payload([[]])


def test_non_dict_message_rejected() -> None:
    with pytest.raises(ExecutionError, match="must be a dict"):
        normalize_prompt_payload([["not-a-dict"]])


def test_missing_role_rejected() -> None:
    with pytest.raises(ExecutionError, match="must have string"):
        normalize_prompt_payload([[{"content": "hi"}]])


def test_missing_content_rejected() -> None:
    with pytest.raises(ExecutionError, match="must have string"):
        normalize_prompt_payload([[{"role": "user"}]])


def test_non_string_role_rejected() -> None:
    with pytest.raises(ExecutionError, match="must have string"):
        normalize_prompt_payload([[{"role": 1, "content": "hi"}]])


def test_non_string_content_rejected() -> None:
    with pytest.raises(ExecutionError, match="must have string"):
        normalize_prompt_payload([[{"role": "user", "content": ["multipart"]}]])


def test_must_end_with_user_role() -> None:
    with pytest.raises(ExecutionError, match="last message"):
        normalize_prompt_payload(
            [
                [
                    {"role": "user", "content": "q"},
                    {"role": "assistant", "content": "a"},
                ]
            ]
        )


def test_assistant_only_item_rejected() -> None:
    with pytest.raises(ExecutionError, match="last message"):
        normalize_prompt_payload([[{"role": "assistant", "content": "?"}]])


# ---- Cross-item system-prompt consistency -----------------------------


def test_baseline_system_then_no_system_rejected() -> None:
    items = [
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "a"},
        ],
        [{"role": "user", "content": "b"}],
    ]
    with pytest.raises(ExecutionError, match="is present"):
        normalize_prompt_payload(items)


def test_baseline_no_system_then_system_rejected() -> None:
    items = [
        [{"role": "user", "content": "a"}],
        [
            {"role": "system", "content": "s"},
            {"role": "user", "content": "b"},
        ],
    ]
    with pytest.raises(ExecutionError, match="not present"):
        normalize_prompt_payload(items)
