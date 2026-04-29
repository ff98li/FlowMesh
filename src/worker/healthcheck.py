import os
import sys
import time

from .utils.health import get_hb_config


def main() -> int:
    _, hb_ttl, hb_file = get_hb_config()
    try:
        mtime = os.path.getmtime(hb_file)
    except OSError:
        return 1
    return 0 if (time.time() - mtime) < hb_ttl else 1


if __name__ == "__main__":
    sys.exit(main())
