import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from unittest.mock import MagicMock, patch

import pytest

from celery_ecs_autoscaler import QueueSource, RabbitMQQueueSource, RedisQueueSource


def test_redis_satisfies_protocol():
    source = RedisQueueSource(broker_url="redis://localhost:6379/0", queue_names=["celery"])
    assert isinstance(source, QueueSource)


def test_rabbitmq_satisfies_protocol():
    source = RabbitMQQueueSource(
        management_url="http://guest:guest@localhost:15672", queue_names=["celery"]
    )
    assert isinstance(source, QueueSource)


def test_redis_get_depth_sums_queues():
    mock_client = MagicMock()
    mock_client.llen.side_effect = lambda name: {"q1": 3, "q2": 5}.get(name, 0)

    with patch("redis.Redis.from_url", return_value=mock_client):
        source = RedisQueueSource(broker_url="redis://localhost/0", queue_names=["q1", "q2"])
        assert source.get_depth() == 8

    mock_client.close.assert_called_once()


def test_redis_get_depth_closes_client_on_error():
    mock_client = MagicMock()
    mock_client.llen.side_effect = RuntimeError("connection refused")

    with patch("redis.Redis.from_url", return_value=mock_client):
        source = RedisQueueSource(broker_url="redis://localhost/0", queue_names=["celery"])
        with pytest.raises(RuntimeError):
            source.get_depth()

    mock_client.close.assert_called_once()


def _make_rabbitmq_handler(queue_depths: dict[str, int]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            queue_name = self.path.split("/")[-1]
            body = json.dumps({"messages_ready": queue_depths.get(queue_name, 0)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    return Handler


def test_rabbitmq_get_depth_sums_queues():
    handler = _make_rabbitmq_handler({"celery": 4, "priority": 6})
    server = HTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t1 = Thread(target=server.handle_request)
    t2 = Thread(target=server.handle_request)
    t1.start()
    t2.start()

    source = RabbitMQQueueSource(
        management_url=f"http://127.0.0.1:{port}",
        queue_names=["celery", "priority"],
    )
    assert source.get_depth() == 10

    t1.join()
    t2.join()
    server.server_close()
