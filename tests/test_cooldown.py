from celery_ecs_autoscaler import CooldownStore, ScalingAction


def test_not_active_before_first_scale():
    store = CooldownStore()
    assert not store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1000.0)


def test_active_immediately_after_scale():
    store = CooldownStore()
    store.mark_scaled("worker", ScalingAction.SCALE_OUT, now=1000.0)
    assert store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1001.0)


def test_expires_after_period():
    store = CooldownStore()
    store.mark_scaled("worker", ScalingAction.SCALE_OUT, now=1000.0)
    assert not store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1061.0)


def test_independent_per_target():
    store = CooldownStore()
    store.mark_scaled("worker-a", ScalingAction.SCALE_OUT, now=1000.0)
    assert not store.active("worker-b", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1001.0)
    assert store.active("worker-a", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1001.0)


def test_scale_out_does_not_block_scale_in():
    store = CooldownStore()
    store.mark_scaled("worker", ScalingAction.SCALE_OUT, now=1000.0)
    assert store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60, now=1001.0)
    assert not store.active("worker", ScalingAction.SCALE_IN, cooldown_seconds=120, now=1001.0)


def test_not_active_before_first_scale_realtime():
    store = CooldownStore()
    assert not store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60)


def test_active_immediately_after_scale_realtime():
    store = CooldownStore()
    store.mark_scaled("worker", ScalingAction.SCALE_OUT)
    assert store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=60)


def test_zero_seconds_is_never_active():
    store = CooldownStore()
    store.mark_scaled("worker", ScalingAction.SCALE_OUT)
    assert not store.active("worker", ScalingAction.SCALE_OUT, cooldown_seconds=0)
