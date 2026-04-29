import logging
from pathlib import Path

from ..base_executor import TaskReference
from ..utils.checkpoints import (
    cleanup_artifact_path,
    get_http_destination,
    is_cleanup_enabled,
)

logger = logging.getLogger("worker.training_mixin")


class TrainingMixin:
    """
    A mixin that implements common training functionalities.
    """

    name = "training_mixin"

    def _cleanup_local_artifacts(
        self,
        task: TaskReference,
        checkpoint_dir: Path,
        final_model_path: Path | None,
        final_archive_path: Path | None,
    ) -> None:
        if not is_cleanup_enabled():
            logger.info(
                "Skipping %s checkpoint cleanup for task %s because "
                "MODEL_CLEANUP_AFTER_UPLOAD is disabled",
                self.name,
                task.task_id,
            )
            return
        if not get_http_destination(task.spec):
            return
        if final_archive_path is None or not final_archive_path.exists():
            logger.info(
                "Skipping checkpoint cleanup for task %s because no uploaded "
                "archive exists",
                task.task_id,
            )
            return
        cleanup_artifact_path(final_model_path, logger=logger)
        cleanup_artifact_path(final_archive_path, logger=logger)
        cleanup_artifact_path(checkpoint_dir, logger=logger)
        if not checkpoint_dir.exists():
            logger.info(
                "Deleted local %s checkpoints for task %s at %s",
                self.name,
                task.task_id,
                checkpoint_dir,
            )
