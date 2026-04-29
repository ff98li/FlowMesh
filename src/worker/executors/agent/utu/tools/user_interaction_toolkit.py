import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from ..config import ToolkitConfig
from ..utils import PrintUtils
from .base import AsyncBaseToolkit, register_tool


class UserInteractionToolkit(AsyncBaseToolkit):
    def __init__(self, config: ToolkitConfig | None = None):
        super().__init__(config)
        self.ask_function: Callable[[str], str] | Callable[[str], Awaitable[str]] = (
            PrintUtils.async_print_input
        )

    def set_ask_function(self, ask_function: Callable[[str], str]):
        self.ask_function = ask_function

    @register_tool
    async def ask_user(self, question: str) -> str:
        """Asks for user's input on a specific question

        Args:
            question (str): The question to ask.
        """
        ret = self.ask_function(question)
        if inspect.isawaitable(ret):
            return await ret
        return ret

    @register_tool
    async def final_answer(self, answer: Any) -> str:
        """Provides a final answer to the given problem.

        Args:
            answer (any): The answer to ask.
        """
        return answer
