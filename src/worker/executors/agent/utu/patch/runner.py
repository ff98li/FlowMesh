import asyncio
import logging
from typing import Any

from agents import (
    Agent,
    ItemHelpers,
    RunConfig,
    RunContextWrapper,
    RunHooks,
    RunItem,
    Tool,
    TResponseInputItem,
)
from agents._run_impl import AgentToolUseTracker, SingleStepResult
from agents.run import AgentRunner, _ServerConversationTracker
from agents.run_context import AgentHookContext
from agents.util import _coro

from ..context import BaseContextManager

logger = logging.getLogger(__name__)


class UTUAgentRunner(AgentRunner):
    # TODO: also add context_manager to _run_single_turn_streamed for .run_streamed
    @classmethod
    async def _run_single_turn(
        cls,
        *,
        agent: Agent[Any],
        all_tools: list[Tool],
        original_input: str | list[TResponseInputItem],
        generated_items: list[RunItem],
        hooks: RunHooks[Any],
        context_wrapper: RunContextWrapper[Any],
        run_config: RunConfig,
        should_run_agent_start_hooks: bool,
        tool_use_tracker: AgentToolUseTracker,
        server_conversation_tracker: _ServerConversationTracker | None = None,
    ) -> SingleStepResult:
        # Ensure we run the hooks before anything else
        if should_run_agent_start_hooks:
            agent_hook_context: AgentHookContext[Any] = AgentHookContext(
                context=context_wrapper.context,
                usage=context_wrapper.usage,
                turn_input=ItemHelpers.input_to_new_input_list(original_input),
            )
            await asyncio.gather(
                hooks.on_agent_start(agent_hook_context, agent),
                (
                    agent.hooks.on_start(agent_hook_context, agent)
                    if agent.hooks
                    else _coro.noop_coroutine()
                ),
            )

        system_prompt, prompt_config = await asyncio.gather(
            agent.get_system_prompt(context_wrapper),
            agent.get_prompt(context_wrapper),
        )

        output_schema = cls._get_output_schema(agent)
        handoffs = await cls._get_handoffs(agent, context_wrapper)
        if server_conversation_tracker is not None:
            input = server_conversation_tracker.prepare_input(
                original_input, generated_items
            )
        else:
            input = ItemHelpers.input_to_new_input_list(original_input)
            input.extend(
                [generated_item.to_input_item() for generated_item in generated_items]
            )

        # FIXME: set context manage as a hook?
        # ADD: context manager
        context_manager: BaseContextManager | None = None
        if context_wrapper.context:
            context_manager = context_wrapper.context.get("context_manager", None)
        if context_manager:
            tmp_input = context_manager.preprocess(input, context_wrapper)
            assert not isinstance(tmp_input, str)
            input = tmp_input
        # print(f"< [DEBUG] input: {input}")
        new_response = await cls._get_new_response(
            agent,
            system_prompt,
            input,
            output_schema,
            all_tools,
            handoffs,
            hooks,
            context_wrapper,
            run_config,
            tool_use_tracker,
            server_conversation_tracker,
            prompt_config,
        )

        # ADD: response logging
        # print(
        #     json.dumps(
        #         [item.model_dump() for item in new_response.output],
        #         ensure_ascii=False,
        #     )
        # )

        single_turn_result = await cls._get_single_step_result_from_response(
            agent=agent,
            original_input=original_input,
            pre_step_items=generated_items,
            new_response=new_response,
            output_schema=output_schema,
            all_tools=all_tools,
            handoffs=handoffs,
            hooks=hooks,
            context_wrapper=context_wrapper,
            run_config=run_config,
            tool_use_tracker=tool_use_tracker,
        )
        # ADD: postprocess
        if context_manager:
            single_turn_result = context_manager.process(single_turn_result)
        return single_turn_result
