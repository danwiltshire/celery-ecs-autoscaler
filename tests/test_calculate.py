import pytest

from celery_ecs_autoscaler import ScalingAction, calculate_next_ecs_task_count


@pytest.mark.parametrize(
    ("queued", "current", "expected_action", "expected_next"),
    [
        (0, 1, ScalingAction.HOLD, 1),  # queue empty at min tasks
        (3, 1, ScalingAction.HOLD, 1),  # light load within deadband (3/8=0.375)
        (6, 1, ScalingAction.HOLD, 1),  # pressure exactly at target (0.75) — not strictly above
        (7, 1, ScalingAction.SCALE_OUT, 2),  # pressure just above target → scale out by step
        (40, 2, ScalingAction.SCALE_OUT, 4),  # heavy backlog, limited by scale_out_step
        (0, 4, ScalingAction.SCALE_IN, 3),  # backlog drains → scale in by 1
    ],
)
def test_scaling_action(queued, current, expected_action, expected_next):
    decision = calculate_next_ecs_task_count(
        queued=queued,
        current_ecs_tasks=current,
        worker_concurrency=8,
    )
    assert decision.action == expected_action
    assert decision.next_tasks == expected_next


def test_scale_out_capped_at_max_tasks():
    decision = calculate_next_ecs_task_count(
        queued=1000,
        current_ecs_tasks=20,
        worker_concurrency=8,
        max_tasks=20,
    )
    assert decision.next_tasks == 20
    assert decision.action == ScalingAction.HOLD


def test_scale_in_never_goes_below_min_tasks():
    decision = calculate_next_ecs_task_count(
        queued=0,
        current_ecs_tasks=1,
        worker_concurrency=8,
        min_tasks=1,
    )
    assert decision.next_tasks == 1
    assert decision.action == ScalingAction.HOLD


def test_scale_out_step_limits_single_jump():
    decision = calculate_next_ecs_task_count(
        queued=100,
        current_ecs_tasks=1,
        worker_concurrency=8,
        scale_out_step=2,
    )
    # desired_tasks = ceil(100 / (8 * 0.75)) = 17, but step caps it at 1+2=3
    assert decision.next_tasks == 3
    assert decision.action == ScalingAction.SCALE_OUT


def test_scale_in_step_limits_single_drop():
    decision = calculate_next_ecs_task_count(
        queued=0,
        current_ecs_tasks=10,
        worker_concurrency=8,
        scale_in_step=1,
    )
    assert decision.next_tasks == 9
    assert decision.action == ScalingAction.SCALE_IN


def test_current_pressure_calculation():
    # 6 queued, 1 task, concurrency 8 → pressure = 6/8 = 0.75 (at target, not above)
    decision = calculate_next_ecs_task_count(
        queued=6,
        current_ecs_tasks=1,
        worker_concurrency=8,
        target_pressure=0.75,
    )
    assert decision.current_pressure == pytest.approx(0.75)
    assert decision.action == ScalingAction.HOLD


def test_desired_tasks_reflects_ideal_count():
    # 12 queued, concurrency 8, target 0.75 → ideal = ceil(12 / 6) = 2
    decision = calculate_next_ecs_task_count(
        queued=12,
        current_ecs_tasks=1,
        worker_concurrency=8,
        target_pressure=0.75,
    )
    assert decision.desired_tasks == 2


def test_scale_to_zero_when_queue_empty():
    decision = calculate_next_ecs_task_count(
        queued=0,
        current_ecs_tasks=1,
        worker_concurrency=8,
        min_tasks=0,
        scale_in_step=1,
    )
    assert decision.action == ScalingAction.SCALE_IN
    assert decision.next_tasks == 0


def test_scale_out_from_zero():
    # current_ecs_tasks=0 clamped to max(min_tasks=0, 0)=0, slots = max(1, 0*8)=1
    decision = calculate_next_ecs_task_count(
        queued=5,
        current_ecs_tasks=0,
        worker_concurrency=8,
        min_tasks=0,
    )
    assert decision.action == ScalingAction.SCALE_OUT
    assert decision.next_tasks >= 1


def test_reason_str_scale_out():
    decision = calculate_next_ecs_task_count(queued=7, current_ecs_tasks=1, worker_concurrency=8)
    assert ">" in str(decision.reason)
    assert "target" in str(decision.reason)


def test_reason_str_scale_in():
    decision = calculate_next_ecs_task_count(queued=0, current_ecs_tasks=4, worker_concurrency=8)
    assert "scale-in threshold" in str(decision.reason)


def test_reason_str_hold_deadband():
    decision = calculate_next_ecs_task_count(queued=3, current_ecs_tasks=1, worker_concurrency=8)
    assert "deadband" in str(decision.reason)


def test_reason_str_clamped():
    decision = calculate_next_ecs_task_count(
        queued=0, current_ecs_tasks=1, worker_concurrency=8, min_tasks=1
    )
    assert "clamped" in str(decision.reason)


def test_invalid_queued_negative():
    with pytest.raises(ValueError, match="queued"):
        calculate_next_ecs_task_count(queued=-1, current_ecs_tasks=1, worker_concurrency=8)


def test_invalid_current_ecs_tasks_negative():
    with pytest.raises(ValueError, match="current_ecs_tasks"):
        calculate_next_ecs_task_count(queued=0, current_ecs_tasks=-1, worker_concurrency=8)


def test_invalid_worker_concurrency_zero():
    with pytest.raises(ValueError, match="worker_concurrency"):
        calculate_next_ecs_task_count(queued=0, current_ecs_tasks=1, worker_concurrency=0)


def test_invalid_target_pressure_zero():
    with pytest.raises(ValueError, match="target_pressure"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, target_pressure=0.0
        )


def test_invalid_target_pressure_above_one():
    with pytest.raises(ValueError, match="target_pressure"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, target_pressure=1.1
        )


def test_invalid_scale_in_pressure_negative():
    with pytest.raises(ValueError, match="scale_in_pressure"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, scale_in_pressure=-0.1
        )


def test_invalid_scale_in_pressure_gte_target():
    with pytest.raises(ValueError, match="scale_in_pressure"):
        calculate_next_ecs_task_count(
            queued=0,
            current_ecs_tasks=1,
            worker_concurrency=8,
            target_pressure=0.5,
            scale_in_pressure=0.5,
        )


def test_invalid_min_tasks_negative():
    with pytest.raises(ValueError, match="min_tasks"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, min_tasks=-1
        )


def test_invalid_max_tasks_less_than_min():
    with pytest.raises(ValueError, match="max_tasks"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, min_tasks=5, max_tasks=3
        )


def test_invalid_scale_out_step_zero():
    with pytest.raises(ValueError, match="scale_out_step"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, scale_out_step=0
        )


def test_invalid_scale_in_step_zero():
    with pytest.raises(ValueError, match="scale_in_step"):
        calculate_next_ecs_task_count(
            queued=0, current_ecs_tasks=1, worker_concurrency=8, scale_in_step=0
        )
