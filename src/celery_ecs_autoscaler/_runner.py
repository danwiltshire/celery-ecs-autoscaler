import logging
import time

import boto3

from celery_ecs_autoscaler.config import AppConfig
from celery_ecs_autoscaler.scaler import CooldownStore, run_target_once

logger = logging.getLogger(__name__)


def run(config: AppConfig) -> None:
    """Start the autoscaler polling loop.

    Blocks indefinitely, polling every ``config.poll_seconds`` seconds.
    Call ``config.validate()`` before passing it in, or let this function do it.

    Example::

        from celery_ecs_autoscaler import (
            AppConfig, EcsServiceTarget, RedisQueueSource, ScalingTarget, run
        )

        config = AppConfig(
            poll_seconds=15,
            dry_run=False,
            targets=[
                ScalingTarget(
                    name="workers",
                    source=RedisQueueSource(broker_url="redis://...", queue_names=["celery"]),
                    ecs=EcsServiceTarget(
                        cluster_name="my-cluster", service_name="workers", worker_concurrency=8
                    ),
                ),
            ],
        )
        run(config)
    """
    config.validate()

    if config.dry_run:
        logger.info("DRY RUN mode — no ECS updates will be made", extra={"dry_run": True})

    ecs_client = boto3.client("ecs")  # region from instance metadata / AWS_DEFAULT_REGION env var
    cooldown_store = CooldownStore()

    while True:
        for target in config.targets:
            if not target.enabled:
                logger.info("target disabled", extra={"target": target.name})
                continue
            try:
                result = run_target_once(
                    ecs_client=ecs_client,
                    target=target,
                    cooldown_store=cooldown_store,
                    dry_run=config.dry_run,
                )
                logger.info(
                    "scaling poll",
                    extra={
                        "target": result.target,
                        "queued": result.queued,
                        "queue_names": result.queue_names,
                        "ecs_running": result.ecs.running,
                        "ecs_desired": result.ecs.desired,
                        "ecs_pending": result.ecs.pending,
                        "action": result.decision.action.value,
                        "next_tasks": result.decision.next_tasks,
                        "pressure": round(result.decision.current_pressure, 4),
                        "reason": str(result.decision.reason),
                        "updated": result.updated,
                        "update_reason": result.update_reason,
                        "dry_run": result.dry_run,
                        "cooldown_active": result.cooldown_active,
                    },
                )
            except Exception as exc:
                logger.exception(
                    "error processing target",
                    extra={"target": target.name, "error": str(exc)},
                )

        time.sleep(config.poll_seconds)
