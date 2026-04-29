import os
from pathlib import Path


def get_hb_config() -> tuple[int, int, Path]:
    """Get heartbeat configuration from environment variables.

    Returns:
        A tuple containing:
            - Heartbeat interval in seconds (int)
            - Heartbeat TTL in seconds (int)
            - Heartbeat file path (Path)
    """
    hb_interval_str = os.getenv("HEARTBEAT_INTERVAL_SEC", "30")
    try:
        hb_interval = int(hb_interval_str)
    except ValueError:
        hb_interval = 30
    hb_ttl = max(hb_interval * 4, 120)
    hb_file = os.getenv("WORKER_HB_FILE")
    if not hb_file:
        raise SystemExit("WORKER_HB_FILE is required")
    return hb_interval, hb_ttl, Path(hb_file).absolute()
