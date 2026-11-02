"""Tiny in-memory stand-in for the confluent_kafka API subset used by kafka_service (tests only)."""

import threading
import time
from types import SimpleNamespace


class Broker:
    def __init__(self) -> None:
        self.topics: dict[str, list[list[tuple]]] = {}
        self.committed: dict[tuple[str, str, int], int] = {}
        self.lock = threading.Lock()

    def ensure(self, topic: str, partitions: int = 1) -> None:
        with self.lock:
            self.topics.setdefault(topic, [[] for _ in range(partitions)])


BROKER = Broker()


class Msg:
    def __init__(self, topic, partition, offset, key, value):
        self._t, self._p, self._o, self._k, self._v = topic, partition, offset, key, value

    def topic(self): return self._t
    def partition(self): return self._p
    def offset(self): return self._o
    def key(self): return self._k
    def value(self): return self._v
    def error(self): return None


class Producer:
    def __init__(self, conf): pass

    def produce(self, topic, key=None, value=None):
        BROKER.ensure(topic)
        parts = BROKER.topics[topic]
        p = (hash(key) % len(parts)) if key else 0
        with BROKER.lock:
            parts[p].append((key, value))

    def flush(self, timeout=None): return 0


class TopicPartition:
    def __init__(self, topic, partition, offset=-1001):
        self.topic, self.partition, self.offset = topic, partition, offset


class Consumer:
    def __init__(self, conf):
        self.group = conf.get("group.id")
        self.assigned: list[TopicPartition] = []
        self.pos: dict[tuple[str, int], int] = {}
        self.on_assign = None

    def subscribe(self, topics, on_assign=None):
        for t in topics:
            BROKER.ensure(t)
        self.assigned = [TopicPartition(t, p) for t in topics for p in range(len(BROKER.topics[t]))]
        for tp in self.assigned:
            self.pos[(tp.topic, tp.partition)] = BROKER.committed.get((self.group, tp.topic, tp.partition), 0)
        if on_assign:
            on_assign(self, self.assigned)

    def assign(self, tps):
        self.assigned = tps
        for tp in tps:
            self.pos[(tp.topic, tp.partition)] = tp.offset

    def list_topics(self, topic=None, timeout=None):
        BROKER.ensure(topic)
        return SimpleNamespace(topics={topic: SimpleNamespace(partitions={i: None for i in range(len(BROKER.topics[topic]))})})

    def get_watermark_offsets(self, tp, timeout=None):
        return 0, len(BROKER.topics[tp.topic][tp.partition])

    def poll(self, timeout=1.0):
        end = time.time() + timeout
        while time.time() < end:
            for tp in self.assigned:
                key = (tp.topic, tp.partition)
                log = BROKER.topics[tp.topic][tp.partition]
                if self.pos[key] < len(log):
                    k, v = log[self.pos[key]]
                    m = Msg(tp.topic, tp.partition, self.pos[key], k, v)
                    self.pos[key] += 1
                    return m
            time.sleep(0.01)
        return None

    def commit(self, message=None, asynchronous=True):
        BROKER.committed[(self.group, message.topic(), message.partition())] = message.offset() + 1

    def close(self): pass


class AdminClient:
    def __init__(self, conf): pass

    def list_topics(self, timeout=None):
        return SimpleNamespace(topics=dict.fromkeys(BROKER.topics))

    def create_topics(self, new):
        out = {}
        for nt in new:
            BROKER.ensure(nt.topic, nt.num_partitions)
            fut = SimpleNamespace(result=lambda: None)
            out[nt.topic] = fut
        return out
