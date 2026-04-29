"""Plugin hooks for extending the server.

- `IdentityProvider` — resolve a bearer token to a `PrincipalContext`.
- `SubmissionGuard` — gate workflow submission.
- `UsageSink` — fan-out per-task usage rows.

Plugins append to the module-level lists; core iterates them at call time.
"""

from .identity import IdentityProvider
from .submission import SubmissionGuard
from .usage import UsageRow, UsageSink

IDENTITY_PROVIDERS: list[IdentityProvider] = []
SUBMISSION_GUARDS: list[SubmissionGuard] = []
USAGE_SINKS: list[UsageSink] = []

__all__ = [
    "UsageRow",
    "IDENTITY_PROVIDERS",
    "IdentityProvider",
    "SUBMISSION_GUARDS",
    "SubmissionGuard",
    "USAGE_SINKS",
    "UsageSink",
]
