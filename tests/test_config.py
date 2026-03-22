import pytest

from celery_ecs_autoscaler import AppConfig, EcsServiceTarget


def test_app_config_validate_passes(minimal_target):
    AppConfig(targets=[minimal_target()]).validate()


def test_app_config_validate_no_targets():
    with pytest.raises(ValueError, match="at least one"):
        AppConfig(targets=[]).validate()


def test_app_config_validate_duplicate_target_names(minimal_target):
    with pytest.raises(ValueError, match="duplicate target name"):
        AppConfig(targets=[minimal_target(), minimal_target()]).validate()


def test_app_config_validate_empty_queue_names(minimal_target):
    with pytest.raises(ValueError, match="queue_names must not be empty"):
        AppConfig(targets=[minimal_target(queue_names=[])]).validate()


def test_app_config_validate_poll_seconds(minimal_target):
    with pytest.raises(ValueError, match="poll_seconds"):
        AppConfig(poll_seconds=0, targets=[minimal_target()]).validate()


def test_ecs_target_validate_worker_concurrency():
    with pytest.raises(ValueError, match="worker_concurrency"):
        EcsServiceTarget(cluster_name="c", service_name="s", worker_concurrency=0).validate()


def test_ecs_target_validate_target_pressure_zero():
    with pytest.raises(ValueError, match="target_pressure"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, target_pressure=0.0
        ).validate()


def test_ecs_target_validate_target_pressure_above_one():
    with pytest.raises(ValueError, match="target_pressure"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, target_pressure=1.1
        ).validate()


def test_ecs_target_validate_scale_in_pressure_negative():
    with pytest.raises(ValueError, match="scale_in_pressure"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, scale_in_pressure=-0.1
        ).validate()


def test_ecs_target_validate_scale_in_pressure_gte_target():
    with pytest.raises(ValueError, match="scale_in_pressure"):
        EcsServiceTarget(
            cluster_name="c",
            service_name="s",
            worker_concurrency=4,
            target_pressure=0.5,
            scale_in_pressure=0.5,
        ).validate()


def test_ecs_target_validate_min_tasks_negative():
    with pytest.raises(ValueError, match="min_tasks"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, min_tasks=-1
        ).validate()


def test_ecs_target_validate_max_tasks_less_than_min():
    with pytest.raises(ValueError, match="max_tasks"):
        EcsServiceTarget(
            cluster_name="c",
            service_name="s",
            worker_concurrency=4,
            min_tasks=5,
            max_tasks=4,
        ).validate()


def test_ecs_target_validate_scale_out_step_zero():
    with pytest.raises(ValueError, match="scale_out_step"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, scale_out_step=0
        ).validate()


def test_ecs_target_validate_scale_in_step_zero():
    with pytest.raises(ValueError, match="scale_in_step"):
        EcsServiceTarget(
            cluster_name="c", service_name="s", worker_concurrency=4, scale_in_step=0
        ).validate()


def test_ecs_target_validate_negative_scale_out_cooldown():
    with pytest.raises(ValueError, match="scale_out_cooldown_seconds"):
        EcsServiceTarget(
            cluster_name="c",
            service_name="s",
            worker_concurrency=4,
            scale_out_cooldown_seconds=-1,
        ).validate()


def test_ecs_target_validate_negative_scale_in_cooldown():
    with pytest.raises(ValueError, match="scale_in_cooldown_seconds"):
        EcsServiceTarget(
            cluster_name="c",
            service_name="s",
            worker_concurrency=4,
            scale_in_cooldown_seconds=-1,
        ).validate()
