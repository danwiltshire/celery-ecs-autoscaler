"""Example autoscaler configuration for a Redis-backed Celery worker fleet.

Copy and adapt this file to your own project, then run:

    python config.py

Set dry_run=False and point cluster_name/service_name at your real ECS service
to start scaling.
"""

from celery_ecs_autoscaler import (
    AppConfig,
    EcsServiceTarget,
    RedisQueueSource,
    ScalingTarget,
    run,
)


def build_config() -> AppConfig:
    return AppConfig(
        poll_seconds=15,
        dry_run=True,  # change to False to apply real ECS updates
        targets=[
            ScalingTarget(
                name="default-celery-workers",
                source=RedisQueueSource(
                    broker_url="redis://localhost:6379/0",
                    queue_names=["celery"],
                ),
                ecs=EcsServiceTarget(
                    cluster_name="my-cluster",
                    service_name="celery-workers",
                    worker_concurrency=8,
                    min_tasks=1,
                    max_tasks=20,
                    target_pressure=0.75,
                    scale_in_pressure=0.25,
                    scale_out_step=2,
                    scale_in_step=1,
                    scale_out_cooldown_seconds=60,
                    scale_in_cooldown_seconds=120,
                ),
            ),
        ],
    )


if __name__ == "__main__":
    run(build_config())
