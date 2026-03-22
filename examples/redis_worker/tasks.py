from time import sleep

from examples.redis_worker.celery_app import app


@app.task
def sample_task(job_number: int) -> dict:
    sleep(2)
    return {"job_number": job_number, "status": "done"}
