import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import redis


@runtime_checkable
class QueueSource(Protocol):
    queue_names: list[str]

    def get_depth(self) -> int: ...


@dataclass(frozen=True)
class RedisQueueSource:
    broker_url: str
    queue_names: list[str]

    def get_depth(self) -> int:
        client = redis.Redis.from_url(self.broker_url)
        try:
            total = 0
            for queue_name in self.queue_names:
                total += int(client.llen(queue_name) or 0)
            return total
        finally:
            client.close()


@dataclass(frozen=True)
class RabbitMQQueueSource:
    management_url: str  # e.g. "http://guest:guest@rabbitmq:15672"
    queue_names: list[str]
    vhost: str = "/"

    def get_depth(self) -> int:
        total = 0
        vhost_encoded = urllib.parse.quote(self.vhost, safe="")
        for queue_name in self.queue_names:
            url = (
                f"{self.management_url}/api/queues/{vhost_encoded}/{urllib.parse.quote(queue_name)}"
            )
            with urllib.request.urlopen(url) as resp:  # noqa: S310
                data = json.loads(resp.read())
            total += int(data.get("messages_ready", 0))
        return total
