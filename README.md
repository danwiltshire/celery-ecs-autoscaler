# celery-ecs-autoscaler

Queue-depth-driven autoscaler for Celery worker fleets running on AWS ECS.

Monitors Redis or RabbitMQ queue depths and adjusts ECS service `desiredCount` to match load — scaling out when queues grow and scaling in when they drain.

[![CI](https://github.com/danwiltshire/celery-ecs-autoscaler/actions/workflows/ci.yml/badge.svg)](https://github.com/danwiltshire/celery-ecs-autoscaler/actions/workflows/ci.yml)

## Installation

```bash
pip install celery-ecs-autoscaler
```

Requires Python 3.11+. Core dependencies: `boto3`, `redis`.

## Quick start

Write a small config module and call `run()`:

```python
from celery_ecs_autoscaler import (
    AppConfig, EcsServiceTarget, RedisQueueSource, ScalingTarget, run
)

config = AppConfig(
    poll_seconds=15,
    dry_run=False,
    targets=[
        ScalingTarget(
            name="default-workers",
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
            ),
        )
    ],
)

run(config)
```

See [`examples/redis_worker/config.py`](examples/redis_worker/config.py) for a full runnable example.

## Configuration reference

### `AppConfig`

| Field          | Type                  | Default  | Description                                    |
| -------------- | --------------------- | -------- | ---------------------------------------------- |
| `poll_seconds` | `int`                 | `15`     | How often to poll queues and ECS               |
| `dry_run`      | `bool`                | `True`   | Log decisions without calling `update_service` |
| `targets`      | `list[ScalingTarget]` | required | One or more scaling targets                    |

> **IAM permissions required:** the process must be able to call `ecs:DescribeServices` and `ecs:UpdateService`. When running on ECS, attach these to the task role. The AWS region is resolved automatically from the task environment — no explicit configuration needed.

### `EcsServiceTarget`

| Field                        | Type    | Default  | Description                                            |
| ---------------------------- | ------- | -------- | ------------------------------------------------------ |
| `cluster_name`               | `str`   | required | ECS cluster name                                       |
| `service_name`               | `str`   | required | ECS service name                                       |
| `worker_concurrency`         | `int`   | required | Celery `--concurrency` value per task                  |
| `min_tasks`                  | `int`   | `1`      | Minimum desired task count (set `0` for scale-to-zero) |
| `max_tasks`                  | `int`   | `20`     | Maximum desired task count                             |
| `target_pressure`            | `float` | `0.75`   | Scale out when `queued / slots > target_pressure`      |
| `scale_in_pressure`          | `float` | `0.25`   | Scale in when `queued / slots < scale_in_pressure`     |
| `scale_out_step`             | `int`   | `2`      | Max tasks to add per poll                              |
| `scale_in_step`              | `int`   | `1`      | Max tasks to remove per poll                           |
| `scale_out_cooldown_seconds` | `int`   | `60`     | Minimum seconds between scale-out actions              |
| `scale_in_cooldown_seconds`  | `int`   | `120`    | Minimum seconds between scale-in actions               |

### Queue sources

**`RedisQueueSource`** — reads queue depth using `LLEN` (Celery default transport):

```python
RedisQueueSource(broker_url="redis://...", queue_names=["celery", "priority"])
```

**`RabbitMQQueueSource`** — reads `messages_ready` via the RabbitMQ Management HTTP API:

```python
RabbitMQQueueSource(
    management_url="http://user:pass@localhost:15672",
    queue_names=["celery"],
    vhost="/",
)
```

You can also implement your own source by satisfying the `QueueSource` Protocol:

```python
class QueueSource(Protocol):
    queue_names: list[str]
    def get_depth(self) -> int: ...
```

## Scaling algorithm

Each poll:

1. Fetch total queue depth across all configured `queue_names`.
2. Fetch current ECS `desiredCount`.
3. Compute `pressure = queued / (desired_tasks * worker_concurrency)`.
4. **Scale out** if `pressure > target_pressure` (step-limited, cooldown-gated).
5. **Scale in** if `pressure < scale_in_pressure` (step-limited, cooldown-gated).
6. **Hold** otherwise (deadband between the two thresholds).

Scale-out and scale-in cooldowns are tracked independently per target so a scale-in event does not block an urgent scale-out.

## Deployment on ECS

The autoscaler itself runs as a single-instance ECS service. Recommended service settings:

```json
{
    "desiredCount": 1,
    "deploymentConfiguration": {
        "minimumHealthyPercent": 0,
        "maximumPercent": 100
    }
}
```

`minimumHealthyPercent: 0` allows ECS to stop the old task before starting the new one, avoiding a period where two instances run simultaneously (which would cause duplicate scaling decisions).

All scaling decisions are logged as structured JSON to stdout:

```json
{
    "message": "scaling poll",
    "target": "default-workers",
    "queued": 14,
    "action": "scale_out",
    "next_tasks": 4,
    "pressure": 0.4375,
    "updated": true
}
```

## Developing

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

### Setup

```bash
uv sync
uv run pre-commit install
```

### Running tests

```bash
uv run pytest tests/ -v
```

### Linting

[Ruff](https://docs.astral.sh/ruff/) is configured in `pyproject.toml` with a broad ruleset including security checks (`S`/bandit), bugbear, import sorting, and pytest style. Pre-commit runs it automatically on every commit.

To run manually:

```bash
uv run pre-commit run --all-files

```

### Running the example

```bash
docker compose up --build  # starts Redis + a Celery worker
python examples/redis_worker/config.py  # dry-run scaler against the local stack
```

## Licence

MIT
