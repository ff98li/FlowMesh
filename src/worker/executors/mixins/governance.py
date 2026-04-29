import json
import logging
import tempfile
import threading
from collections import defaultdict
from pathlib import Path
from threading import Lock
from typing import Any

import requests

from shared.utils.json import dedup_json, restore_json
from shared.utils.time import now_iso

from ..base_executor import ExecutionError

logger = logging.getLogger(__name__)


class GovernanceMixin:
    """
    Mixin for governance-related operations in FlowMesh.

    This class provides functionality for tracking events, caching governance data,
    and interfacing with external governance APIs for data read/write operations.
    It maintains an event log for audit trails and implements caching mechanisms
    to optimize repeated data fetch operations.

    Attributes:
        _event_log: Thread-safe dictionary storing event logs keyed by data_id
        _current_batch_id: Current batch identifier for grouping related operations
        _event_lock: Threading lock for synchronizing event log access
        _cache_dir: Directory path for caching governance API responses
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._task_id: str | None = None
        self._event_log: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._current_batch_id: str | None = None
        self._event_lock = threading.Lock()
        self._cache_dir = Path(tempfile.gettempdir()) / "flowmesh_governance_cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_dir_lock = Lock()

    # events related methods
    def _clear_events(self) -> None:
        """
        Clear all events from the event log.

        Thread-safe operation that removes all logged events from memory.
        This is typically called when starting a new batch of operations.
        """
        with self._event_lock:
            self._event_log.clear()

    def _log_event(
        self,
        data_id: str = "",
        event_type: str = "",
        event_data: str = "",
        timestamp: str | None = None,
    ) -> None:
        """
        Log an event to the event log for tracking and audit purposes.

        Args:
            data_id: Identifier for the data associated with this event.
                    If empty, uses the current task_id (must be set).
            event_type: Type/category of the event (required).
            event_data: Additional data or context for the event.
            timestamp: ISO format timestamp for the event. If None, uses current
                       UTC time.

        Raises:
            ExecutionError: If event_type is not provided.
            AssertionError: If data_id is not provided and task_id is not set.

        The event is stored thread-safely in the event log with the current batch_id.
        """
        if not data_id:
            assert (
                self._task_id is not None
            ), "data_id must be provided if task_id is not set"
            data_id = self._task_id
        if not event_type:
            raise ExecutionError("event_type must be provided")
        ts_value = timestamp or now_iso()
        event_entry = {
            "event_type": event_type,
            "event_data": event_data,
            "timestamp": ts_value,
            "batch_id": self._current_batch_id,
        }
        with self._event_lock:
            self._event_log[data_id].append(event_entry)
        logger.debug("Logged event for data_id=%s: %s", data_id, event_entry)

    def _get_events(self) -> dict[str, list[dict[str, Any]]]:
        """
        Get a copy of all events in the event log.

        Returns:
            A dictionary containing all logged events, keyed by data_id.
            Each value is a list of event entries with event_type, event_data,
            timestamp, and batch_id information.
        """
        with self._event_lock:
            return dict(self._event_log)

    def _events_for(
        self, data_ids: list[str] | set[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Return a filtered view of the event log for the given data ids.

        Args:
            data_ids: List or set of data identifiers to filter events by.
                     If empty or None, returns an empty dictionary.

        Returns:
            A dictionary containing only the events for the specified data_ids,
            with the same structure as the full event log.
        """
        wanted = {str(x) for x in (data_ids or [])}
        if not wanted:
            return {}
        with self._event_lock:
            return {k: v for k, v in self._event_log.items() if k in wanted}

    def _parse_spec(self, governance_spec: dict[str, Any]) -> tuple[str, str, str]:
        """
        Parse and validate governance specification dictionary.

        Args:
            governance_spec: Dictionary containing governance configuration with
                           required fields: 'url', 'user_id', and 'trace_id'.

        Returns:
            A tuple of (governance_url, user_id, trace_id) extracted from the spec.

        Raises:
            ExecutionError: If any required field (url, user_id, trace_id) is missing.
        """
        governance_url = governance_spec.get("url")
        user_id = governance_spec.get("user_id")
        trace_id = governance_spec.get("trace_id")
        if not governance_url or not user_id or not trace_id:
            raise ExecutionError(
                f"Governance spec missing required fields: {governance_spec}"
            )
        return governance_url, user_id, trace_id

    def _fetch_data(
        self, data_id: str, governance_spec: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Fetch data from governance API with caching support.

        This method attempts to retrieve data from a local cache first, and if not found
        or expired, makes an HTTP request to the governance API. It logs various events
        throughout the process for audit trails.

        Args:
            data_id: Unique identifier for the data to fetch.
            governance_spec: Dictionary containing governance configuration with
                           'url', 'user_id', and 'trace_id' fields.

        Returns:
            The retrieved data as a dictionary, restored from JSON format.

        Raises:
            ExecutionError: If the API request fails, response parsing fails,
                          or trace_id validation fails.

        Notes:
            - Caches responses to avoid redundant API calls
            - Validates that trace_id matches to prevent cross-workflow data access
            - Logs multiple events: request initiation, cache hits, transfers,
              decoding, and caching
        """
        governance_url, user_id, trace_id = self._parse_spec(governance_spec)
        try:
            self._log_event(
                data_id=data_id,
                event_type="read request initiated",
                timestamp=now_iso(),
            )
            cache_path = self._cache_dir / f"{data_id}-{user_id}-{trace_id}.json"
            logger.debug(
                "Governance read: data_id=%s user_id=%s trace_id=%s cache=%s",
                data_id,
                user_id,
                trace_id,
                cache_path.as_posix(),
            )
            with self._cache_dir_lock:
                if cache_path.exists():
                    with open(cache_path, encoding="utf-8") as f:
                        cached = json.load(f)
                    self._log_event(
                        data_id=data_id,
                        event_type="read cache hit",
                        timestamp=now_iso(),
                        event_data="Using cached upstream result",
                    )
                    return cached

            api_url = governance_url.rstrip("/") + "/api/read"
            params = {
                "data_id": data_id,
                "user_id": user_id,
            }
            logger.debug(
                "Governance read request: url=%s params=%s",
                api_url,
                params,
            )
            response = requests.get(api_url, params=params, timeout=30)
            if response.status_code >= 400:
                logger.warning(
                    "Governance read failed (status %s): %s",
                    response.status_code,
                    response.text[:200],
                )
            response.raise_for_status()

            self._log_event(
                data_id=data_id,
                event_type="read response transfer",
                timestamp=now_iso(),
            )

            read_response = response.json()
            # Extract required fields from ReadResponse
            retrieved_data = restore_json(json.loads(read_response["data"]))
            assert (
                trace_id == read_response["trace_id"]
            ), "One workflow should not access data from another workflow"

            self._log_event(
                data_id=data_id,
                event_type="read response decoding",
                timestamp=now_iso(),
            )

            with self._cache_dir_lock:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(retrieved_data, f, ensure_ascii=False)

            self._log_event(
                data_id=data_id,
                event_type="read response cache write",
                timestamp=now_iso(),
            )
            logger.info(
                "Written data %s to cache at %s upon first read",
                data_id,
                cache_path.as_posix(),
            )
        except Exception as exc:
            raise ExecutionError(
                f"Error fetching upstream result {data_id}: {exc}"
            ) from exc

        return retrieved_data

    def _write_data(
        self,
        data_id: str,
        data: Any,
        source_data_ids: list[str],
        governance_spec: dict[str, Any],
        events: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        """
        Write data to governance API with event tracking.

        This method prepares and sends data to the governance API, including
        associated events and metadata. It handles data deduplication and
        provides comprehensive logging for the operation.

        Args:
            data_id: Unique identifier for the data being written.
            data: The data to write (will be JSON serialized).
            source_data_ids: List of data IDs that this data depends on or sources from.
            governance_spec: Dictionary containing governance configuration with
                           'url', 'user_id', and 'trace_id' fields.
            events: Optional dictionary of events to include. If None, automatically
                   collects events for data_id and source_data_ids.

        Returns:
            None. Logs success or warning messages based on API response.

        Notes:
            - Automatically deduplicates JSON data before sending
            - Includes relevant events for audit trails
            - Handles 4xx/5xx responses gracefully with warnings
            - Logs request preparation and success with data size metrics
        """
        governance_url, user_id, trace_id = self._parse_spec(governance_spec)
        cache_path = self._cache_dir / f"{data_id}-{user_id}-{trace_id}.json"
        request_data = {
            "data_id": data_id,
            "user_id": user_id,
            "trace_id": trace_id,
            "data": json.dumps(dedup_json(data), ensure_ascii=False),
            "source_data_ids": source_data_ids or [],
            "events": (
                events
                if events is not None
                else self._events_for([data_id, *(source_data_ids or [])])
            ),
            "batch_id": self._current_batch_id,
        }
        self._log_event(
            data_id=data_id,
            event_type="write request preparation",
            timestamp=now_iso(),
        )

        # Write to cache
        with self._cache_dir_lock:
            assert not cache_path.exists(), "Cache path should not exist before writing"
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        self._log_event(
            data_id=data_id,
            event_type="write request cache write",
            timestamp=now_iso(),
        )
        logger.info(
            "Written data %s to cache at %s during governance write",
            data_id,
            cache_path.as_posix(),
        )

        # Send to governance API
        api_url = governance_url.rstrip("/") + "/api/write"
        response = requests.post(api_url, json=request_data, timeout=300)

        if response.status_code >= 400:
            logger.warning(
                "Governance dump failed for data %s (status %s): %s",
                data_id,
                response.status_code,
                response.text[:200],
            )
            return

        logger.info(
            "Dumped execution result for data %s to governance "
            "(size: %d bytes, items: %d)",
            data_id,
            len(json.dumps(request_data, ensure_ascii=False).encode("utf-8")),
            len(data.get("items", [])),
        )
