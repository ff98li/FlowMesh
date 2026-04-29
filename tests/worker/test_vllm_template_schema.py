"""Tests for ``VLLMExecutor`` structural-output templates + chat-template
kwargs: named-fields list form, raw JSON-schema dict form, and Jinja kwargs
forwarded to ``tokenizer.apply_chat_template``."""

from typing import Any
from unittest.mock import MagicMock

import pytest

pytest.importorskip("vllm", reason="vllm not installed (needs --extra inference-gpu)")
pytest.importorskip("torch", reason="torch not installed (needs --extra inference)")

from tests.worker.factories import DEFAULT_WORKER_CONFIG
from worker.executors.base_executor import ExecutionError
from worker.executors.vllm_executor import VLLMExecutor, _RawJsonSchema


def _executor() -> VLLMExecutor:
    return VLLMExecutor(DEFAULT_WORKER_CONFIG, lifecycle=None)


# ---------------------------------------------------------------------------
# (1) Named-fields form (``templates: list``)
# ---------------------------------------------------------------------------


class TestNamedFieldsForm:
    def test_template_params_cfg_returns_flat_shape(self) -> None:
        cfg = _executor()._template_params_cfg(
            {
                "templates": [
                    {"name": "title", "type": "str"},
                    {"name": "rating", "type": "int", "min": 0, "max": 10},
                ]
            }
        )
        assert isinstance(cfg, dict)
        assert set(cfg.keys()) == {"template", "params", "placeholders"}
        assert cfg["placeholders"] == {"title", "rating"}

    def test_construct_returns_pydantic_kwargs(self) -> None:
        schema = _executor()._construct_template_param_schema(
            {
                "templates": [
                    {"name": "title", "type": "str"},
                    {"name": "rating", "type": "int", "min": 0, "max": 10},
                ]
            }
        )
        assert isinstance(schema, dict)
        assert not isinstance(schema, _RawJsonSchema)
        assert set(schema.keys()) == {"title", "rating"}

    def test_build_sampling_params_uses_pydantic_model_json_schema(self) -> None:
        from pydantic import create_model

        schema_kwargs = _executor()._construct_template_param_schema(
            {
                "templates": [
                    {"name": "title", "type": "str"},
                    {"name": "rating", "type": "int", "min": 0, "max": 10},
                ]
            }
        )
        assert isinstance(schema_kwargs, dict)
        sp = _executor()._build_sampling_params(
            {"temperature": 0.0, "max_tokens": 16}, schema=schema_kwargs
        )
        assert sp.structured_outputs is not None
        expected = create_model("Template", **schema_kwargs).model_json_schema()
        assert sp.structured_outputs.json == expected

    def test_item_without_name_rejected(self) -> None:
        with pytest.raises(ExecutionError, match="must be a mapping with a 'name'"):
            _executor()._template_params_cfg(
                {
                    "templates": [
                        {"name": "ok", "type": "str"},
                        {"type": "str"},
                    ]
                }
            )

    def test_single_item_list_is_still_named_fields(self) -> None:
        # Raw schema is signalled by ``dict``, never by a one-element ``list``.
        cfg = _executor()._template_params_cfg(
            {"templates": [{"name": "only", "type": "str"}]}
        )
        assert isinstance(cfg, dict)
        assert cfg["placeholders"] == {"only"}


# ---------------------------------------------------------------------------
# (2) Raw JSON-schema path
# ---------------------------------------------------------------------------


_NESTED_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "explanation": {"type": "string"},
                },
                "required": ["summary", "explanation"],
            },
        }
    },
    "required": ["findings"],
}


class TestRawJsonSchemaForm:
    def test_dict_templates_detected(self) -> None:
        cfg = _executor()._template_params_cfg({"templates": _NESTED_SCHEMA})
        assert isinstance(cfg, _RawJsonSchema)
        assert cfg.schema == _NESTED_SCHEMA

    def test_construct_returns_wrapper(self) -> None:
        schema = _executor()._construct_template_param_schema(
            {"templates": _NESTED_SCHEMA}
        )
        assert isinstance(schema, _RawJsonSchema)
        assert schema.schema == _NESTED_SCHEMA

    def test_build_sampling_params_uses_raw_schema_directly(self) -> None:
        wrapped = _executor()._construct_template_param_schema(
            {"templates": _NESTED_SCHEMA}
        )
        assert isinstance(wrapped, _RawJsonSchema)
        sp = _executor()._build_sampling_params(
            {"temperature": 0.0, "max_tokens": 16}, schema=wrapped
        )
        assert sp.structured_outputs is not None
        assert sp.structured_outputs.json == _NESTED_SCHEMA

    def test_openai_response_format_wrapper_not_unpacked(self) -> None:
        # Wrappers pass through verbatim; vLLM rejects them at decode time.
        wrapper = {
            "type": "json_schema",
            "json_schema": {"name": "report", "schema": _NESTED_SCHEMA},
        }
        cfg = _executor()._template_params_cfg({"templates": wrapper})
        assert isinstance(cfg, _RawJsonSchema)
        assert cfg.schema == wrapper

    def test_templates_none_returns_none(self) -> None:
        assert _executor()._template_params_cfg({}) is None

    @pytest.mark.parametrize("bad", ["string", 42, 3.14, True, (1, 2)])
    def test_non_dict_non_list_raises(self, bad: Any) -> None:
        with pytest.raises(ExecutionError, match="must be a non-empty dict .* or list"):
            _executor()._template_params_cfg({"templates": bad})

    def test_empty_dict_raises(self) -> None:
        with pytest.raises(ExecutionError, match="must be a non-empty dict .* or list"):
            _executor()._template_params_cfg({"templates": {}})

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ExecutionError, match="must be a non-empty dict .* or list"):
            _executor()._template_params_cfg({"templates": []})


# ---------------------------------------------------------------------------
# (3) chat_template_kwargs passthrough
# ---------------------------------------------------------------------------


def _mock_tokenizer() -> MagicMock:
    tokenizer = MagicMock()
    # Production code gates on ``getattr(tokenizer, "chat_template", None)``.
    tokenizer.chat_template = "<dummy chat template string>"

    def _apply(messages: Any, **kwargs: Any) -> str:
        thinking_flag = kwargs.get("enable_thinking")
        content = messages[-1]["content"]
        return f"<|im_start|>user\n{content}<|im_end|>think={thinking_flag}"

    tokenizer.apply_chat_template = MagicMock(side_effect=_apply)
    return tokenizer


class TestChatTemplateKwargs:
    def test_apply_chat_template_forwards_enable_thinking_false(self) -> None:
        executor = _executor()
        tokenizer = _mock_tokenizer()
        executor._llm = MagicMock()
        executor._llm.get_tokenizer.return_value = tokenizer

        _, rendered = executor._apply_chat_template(
            prompts=["hello"],
            system_prompt=None,
            has_images=False,
            chat_template_kwargs={"enable_thinking": False},
        )

        call_kwargs = tokenizer.apply_chat_template.call_args.kwargs
        assert call_kwargs["tokenize"] is False
        assert call_kwargs["add_generation_prompt"] is True
        assert call_kwargs["enable_thinking"] is False
        assert rendered == ["<|im_start|>user\nhello<|im_end|>think=False"]

    def test_apply_chat_template_without_kwargs_omits_extras(self) -> None:
        executor = _executor()
        tokenizer = _mock_tokenizer()
        executor._llm = MagicMock()
        executor._llm.get_tokenizer.return_value = tokenizer

        executor._apply_chat_template(
            prompts=["hi"],
            system_prompt=None,
        )

        call_kwargs = tokenizer.apply_chat_template.call_args.kwargs
        # Only the two built-in kwargs get passed; no sneak-in of defaults.
        assert set(call_kwargs.keys()) == {"tokenize", "add_generation_prompt"}

    def test_apply_chat_template_forwards_multiple_kwargs(self) -> None:
        executor = _executor()
        tokenizer = _mock_tokenizer()
        executor._llm = MagicMock()
        executor._llm.get_tokenizer.return_value = tokenizer

        executor._apply_chat_template(
            prompts=["hi"],
            system_prompt=None,
            chat_template_kwargs={
                "enable_thinking": False,
                "custom_flag": "value",
            },
        )

        call_kwargs = tokenizer.apply_chat_template.call_args.kwargs
        assert call_kwargs["enable_thinking"] is False
        assert call_kwargs["custom_flag"] == "value"


class TestExtractChatTemplateKwargs:
    def test_missing_key_returns_none(self) -> None:
        assert VLLMExecutor._extract_chat_template_kwargs({}) is None

    def test_explicit_none_returns_none(self) -> None:
        assert (
            VLLMExecutor._extract_chat_template_kwargs({"chat_template_kwargs": None})
            is None
        )

    def test_valid_dict_returned_as_is(self) -> None:
        payload = {"enable_thinking": False}
        assert (
            VLLMExecutor._extract_chat_template_kwargs(
                {"chat_template_kwargs": payload}
            )
            is payload
        )

    def test_empty_dict_returned_as_is(self) -> None:
        assert (
            VLLMExecutor._extract_chat_template_kwargs({"chat_template_kwargs": {}})
            == {}
        )

    @pytest.mark.parametrize("bad_value", [False, 0, "enable_thinking=False", ["x"]])
    def test_non_dict_raises(self, bad_value: Any) -> None:
        with pytest.raises(
            ExecutionError,
            match="spec.inference.chat_template_kwargs must be a mapping",
        ):
            VLLMExecutor._extract_chat_template_kwargs(
                {"chat_template_kwargs": bad_value}
            )

    @pytest.mark.parametrize(
        "reserved_key", ["tokenize", "add_generation_prompt", "messages"]
    )
    def test_reserved_keys_rejected(self, reserved_key: str) -> None:
        with pytest.raises(ExecutionError, match="worker-controlled arguments"):
            VLLMExecutor._extract_chat_template_kwargs(
                {"chat_template_kwargs": {reserved_key: True}}
            )

    def test_reserved_key_error_lists_all_conflicts(self) -> None:
        with pytest.raises(
            ExecutionError,
            match=r"\['add_generation_prompt', 'tokenize'\]",
        ):
            VLLMExecutor._extract_chat_template_kwargs(
                {
                    "chat_template_kwargs": {
                        "tokenize": True,
                        "add_generation_prompt": False,
                        "enable_thinking": False,
                    }
                }
            )
