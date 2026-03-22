from dataclasses import dataclass

from celery_ecs_autoscaler.sources import QueueSource


@dataclass(frozen=True)
class EcsTaskCounts:
    running: int
    desired: int
    pending: int


@dataclass(frozen=True)
class EcsServiceTarget:
    cluster_name: str
    service_name: str
    worker_concurrency: int
    min_tasks: int = 1
    max_tasks: int = 20
    target_pressure: float = 0.75
    scale_in_pressure: float = 0.25
    scale_out_step: int = 2
    scale_in_step: int = 1
    scale_out_cooldown_seconds: int = 60
    scale_in_cooldown_seconds: int = 120

    def validate(self) -> None:
        if self.worker_concurrency <= 0:
            raise ValueError("worker_concurrency must be > 0")
        if not (0 < self.target_pressure <= 1):
            raise ValueError("target_pressure must be > 0 and <= 1")
        if not (0 <= self.scale_in_pressure < self.target_pressure):
            raise ValueError("scale_in_pressure must be >= 0 and < target_pressure")
        if self.min_tasks < 0:
            raise ValueError("min_tasks must be >= 0")
        if self.max_tasks < self.min_tasks:
            raise ValueError("max_tasks must be >= min_tasks")
        if self.scale_out_step <= 0:
            raise ValueError("scale_out_step must be > 0")
        if self.scale_in_step <= 0:
            raise ValueError("scale_in_step must be > 0")
        if self.scale_out_cooldown_seconds < 0:
            raise ValueError("scale_out_cooldown_seconds must be >= 0")
        if self.scale_in_cooldown_seconds < 0:
            raise ValueError("scale_in_cooldown_seconds must be >= 0")


@dataclass(frozen=True)
class ScalingTarget:
    name: str
    source: QueueSource
    ecs: EcsServiceTarget
    enabled: bool = True
