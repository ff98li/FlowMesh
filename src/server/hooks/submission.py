"""Submission-guard hook.

Ran before a workflow submission is parsed. Each guard self-filters by
principal (e.g. a balance guard short-circuits for non-billable orgs)
and raises `HTTPException` to block, returns None to allow.
"""

import logging
from typing import Protocol, runtime_checkable

from ..auth.security import PrincipalContext


@runtime_checkable
class SubmissionGuard(Protocol):
    name: str

    async def check(self, principal: PrincipalContext, logger: logging.Logger) -> None:
        """Reject the submission by raising `HTTPException`, or allow."""
        ...
