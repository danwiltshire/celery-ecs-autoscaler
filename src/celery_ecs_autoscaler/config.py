from dataclasses import dataclass, field

from celery_ecs_autoscaler.targets import ScalingTarget


@dataclass(frozen=True)
class AppConfig:
    poll_seconds: int = 15
    dry_run: bool = True
    targets: list[ScalingTarget] = field(default_factory=list)

    def validate(self) -> None:
        if self.poll_seconds <= 0:
            raise ValueError("poll_seconds must be > 0")
        if not self.targets:
            raise ValueError("at least one scaling target must be configured")

        names: set[str] = set()
        for target in self.targets:
            if target.name in names:
                raise ValueError(f"duplicate target name: {target.name}")
            names.add(target.name)

            if not target.source.queue_names:
                raise ValueError(f"{target.name}: queue_names must not be empty")

            target.ecs.validate()
