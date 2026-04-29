import logging
from logging.handlers import RotatingFileHandler

from shared.schemas.event import NodeEvent, WorkerEvent


def get_logger(
    name: str,
    log_file: str,
    *,
    max_bytes: int,
    backup_count: int,
    level: str,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            try:
                handler.close()
            except Exception:
                pass

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    fh = RotatingFileHandler(
        log_file,
        mode="w",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.addHandler(ch)
    return logger


def log_node_event(logger: logging.Logger, event: NodeEvent) -> None:
    event_type = event.type
    node_id = event.node_id
    if event_type == "SV_REGISTER":
        logger.info("Node registered: id=%s tags=%s", node_id, event.tags)
    elif event_type == "SV_HEARTBEAT":
        logger.debug("Node heartbeat: id=%s", node_id)
    elif event_type == "SV_UNREGISTER":
        logger.info("Node unregistered: id=%s", node_id)


def log_worker_event(logger: logging.Logger, event: WorkerEvent) -> None:
    event_type = event.type
    worker_id = event.worker_id
    if event_type == "REGISTER":
        logger.info(
            "Worker registered: id=%s status=%s tags=%s",
            worker_id,
            event.status,
            event.tags,
        )
    elif event_type == "UNREGISTER":
        logger.info("Worker unregistered: id=%s", worker_id)
    elif event_type == "STATUS":
        logger.debug("Worker status: id=%s status=%s", worker_id, event.status)
    elif event_type == "HEARTBEAT":
        logger.debug("Worker heartbeat: id=%s", worker_id)
