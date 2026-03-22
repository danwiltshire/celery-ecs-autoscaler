import pytest

from celery_ecs_autoscaler import EcsServiceTarget, RedisQueueSource, ScalingTarget


@pytest.fixture
def minimal_target():
    def _make(name: str = "workers", queue_names: list[str] | None = None) -> ScalingTarget:
        return ScalingTarget(
            name=name,
            source=RedisQueueSource(
                broker_url="redis://localhost/0",
                queue_names=["celery"] if queue_names is None else queue_names,
            ),
            ecs=EcsServiceTarget(cluster_name="c", service_name="s", worker_concurrency=4),
        )

    return _make
