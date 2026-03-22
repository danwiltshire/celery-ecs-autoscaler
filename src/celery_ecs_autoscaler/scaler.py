import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from celery_ecs_autoscaler.targets import EcsTaskCounts, ScalingTarget


class ScalingAction(str, Enum):
    SCALE_OUT = "scale_out"
    SCALE_IN = "scale_in"
    HOLD = "hold"


@dataclass(frozen=True)
class ScalingReason:
    action: ScalingAction
    current_pressure: float
    scale_in_threshold: float
    target_pressure: float
    clamped: bool = False

    def __str__(self) -> str:
        if self.action == ScalingAction.SCALE_OUT:
            msg = f"pressure {self.current_pressure:.2f} > target {self.target_pressure:.2f}"
        elif self.action == ScalingAction.SCALE_IN:
            msg = (
                f"pressure {self.current_pressure:.2f} < scale-in threshold "
                f"{self.scale_in_threshold:.2f}"
            )
        else:
            msg = (
                f"pressure {self.current_pressure:.2f} is within deadband "
                f"{self.scale_in_threshold:.2f}..{self.target_pressure:.2f}"
            )
        return f"{msg} (clamped — no change)" if self.clamped else msg


@dataclass(frozen=True)
class ScalingDecision:
    queued: int
    current_pressure: float
    desired_tasks: int
    next_tasks: int
    action: ScalingAction
    reason: ScalingReason


@dataclass(frozen=True)
class ScalingResult:
    target: str
    queued: int
    queue_names: list[str]
    ecs: EcsTaskCounts
    decision: ScalingDecision
    updated: bool
    update_reason: str
    dry_run: bool
    cooldown_active: bool


class CooldownStore:
    def __init__(self) -> None:
        # Key is "<target_name>:<action.value>" so scale-out and scale-in cool down independently.
        self._last_scale_ts: dict[str, float] = {}

    def active(
        self,
        target_name: str,
        action: ScalingAction,
        cooldown_seconds: int,
        now: float | None = None,
    ) -> bool:
        key = f"{target_name}:{action.value}"
        last_ts = self._last_scale_ts.get(key, 0.0)
        t = time.time() if now is None else now
        return (t - last_ts) < cooldown_seconds

    def mark_scaled(
        self, target_name: str, action: ScalingAction, now: float | None = None
    ) -> None:
        key = f"{target_name}:{action.value}"
        self._last_scale_ts[key] = time.time() if now is None else now


def get_running_and_desired_task_count(
    ecs_client: Any,
    cluster_name: str,
    service_name: str,
) -> EcsTaskCounts:
    response = ecs_client.describe_services(
        cluster=cluster_name,
        services=[service_name],
    )
    services = response.get("services") or []

    if not services:
        raise RuntimeError(
            f"ECS service not found: cluster={cluster_name!r}, service={service_name!r}"
        )

    service = services[0]

    return EcsTaskCounts(
        running=int(service.get("runningCount", 0)),
        desired=int(service.get("desiredCount", 0)),
        pending=int(service.get("pendingCount", 0)),
    )


def calculate_next_ecs_task_count(
    queued: int,
    current_ecs_tasks: int,
    worker_concurrency: int,
    target_pressure: float = 0.75,
    scale_in_pressure: float = 0.25,
    min_tasks: int = 1,
    max_tasks: int = 100,
    scale_out_step: int = 2,
    scale_in_step: int = 1,
) -> ScalingDecision:
    if queued < 0:
        raise ValueError("queued must be >= 0")
    if current_ecs_tasks < 0:
        raise ValueError("current_ecs_tasks must be >= 0")
    if worker_concurrency <= 0:
        raise ValueError("worker_concurrency must be > 0")
    if not (0 < target_pressure <= 1):
        raise ValueError("target_pressure must be > 0 and <= 1")
    if not (0 <= scale_in_pressure < target_pressure):
        raise ValueError("scale_in_pressure must be >= 0 and < target_pressure")
    if min_tasks < 0:
        raise ValueError("min_tasks must be >= 0")
    if max_tasks < min_tasks:
        raise ValueError("max_tasks must be >= min_tasks")
    if scale_out_step <= 0:
        raise ValueError("scale_out_step must be > 0")
    if scale_in_step <= 0:
        raise ValueError("scale_in_step must be > 0")

    current_ecs_tasks = max(min_tasks, min(max_tasks, current_ecs_tasks))

    current_slots = max(1, current_ecs_tasks * worker_concurrency)
    current_pressure = queued / current_slots

    desired_tasks = math.ceil(queued / (worker_concurrency * target_pressure)) if queued > 0 else 0
    desired_tasks = max(min_tasks, min(max_tasks, desired_tasks))

    if current_pressure > target_pressure:
        next_tasks = min(desired_tasks, current_ecs_tasks + scale_out_step)
        action = ScalingAction.SCALE_OUT
    elif current_pressure < scale_in_pressure:
        next_tasks = max(desired_tasks, current_ecs_tasks - scale_in_step)
        action = ScalingAction.SCALE_IN
    else:
        next_tasks = current_ecs_tasks
        action = ScalingAction.HOLD

    next_tasks = max(min_tasks, min(max_tasks, next_tasks))

    # After all clamping, if the count didn't actually change the real outcome is hold.
    clamped = next_tasks == current_ecs_tasks and action != ScalingAction.HOLD
    if clamped:
        action = ScalingAction.HOLD

    return ScalingDecision(
        queued=queued,
        current_pressure=current_pressure,
        desired_tasks=desired_tasks,
        next_tasks=next_tasks,
        action=action,
        reason=ScalingReason(
            action=action,
            current_pressure=current_pressure,
            scale_in_threshold=scale_in_pressure,
            target_pressure=target_pressure,
            clamped=clamped,
        ),
    )


def run_target_once(
    ecs_client: Any,
    target: ScalingTarget,
    cooldown_store: CooldownStore,
    dry_run: bool,
) -> ScalingResult:
    queued = target.source.get_depth()

    ecs = get_running_and_desired_task_count(
        ecs_client=ecs_client,
        cluster_name=target.ecs.cluster_name,
        service_name=target.ecs.service_name,
    )

    decision = calculate_next_ecs_task_count(
        queued=queued,
        current_ecs_tasks=ecs.desired,
        worker_concurrency=target.ecs.worker_concurrency,
        target_pressure=target.ecs.target_pressure,
        scale_in_pressure=target.ecs.scale_in_pressure,
        min_tasks=target.ecs.min_tasks,
        max_tasks=target.ecs.max_tasks,
        scale_out_step=target.ecs.scale_out_step,
        scale_in_step=target.ecs.scale_in_step,
    )

    cooldown_seconds = (
        target.ecs.scale_out_cooldown_seconds
        if decision.action == ScalingAction.SCALE_OUT
        else target.ecs.scale_in_cooldown_seconds
    )
    cooldown_active = decision.action != ScalingAction.HOLD and cooldown_store.active(
        target.name, decision.action, cooldown_seconds
    )
    updated = False

    if cooldown_active:
        update_reason = "cooldown active"
    elif dry_run:
        update_reason = "dry run"
    elif decision.next_tasks != ecs.desired:
        ecs_client.update_service(
            cluster=target.ecs.cluster_name,
            service=target.ecs.service_name,
            desiredCount=decision.next_tasks,
        )
        cooldown_store.mark_scaled(target.name, decision.action)
        updated = True
        update_reason = f"updated desired count from {ecs.desired} to {decision.next_tasks}"
    else:
        update_reason = "desired count unchanged"

    return ScalingResult(
        target=target.name,
        queued=queued,
        queue_names=target.source.queue_names,
        ecs=ecs,
        decision=decision,
        updated=updated,
        update_reason=update_reason,
        dry_run=dry_run,
        cooldown_active=cooldown_active,
    )
