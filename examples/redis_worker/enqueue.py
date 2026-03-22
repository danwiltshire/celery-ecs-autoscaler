"""Enqueue sample tasks to test auto-scaling locally.

Usage:
    PYTHONPATH=. python examples/redis_worker/enqueue.py
"""

from examples.redis_worker.tasks import sample_task


def enqueue_jobs(count: int = 50) -> list[str]:
    return [sample_task.delay(i).id for i in range(count)]


if __name__ == "__main__":
    ids = enqueue_jobs(50)
    print(f"Enqueued {len(ids)} jobs")
