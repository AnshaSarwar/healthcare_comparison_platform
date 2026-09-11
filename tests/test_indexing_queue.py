from uuid import uuid4

from backend.workers.indexing_queue import QUEUE_KEY, enqueue_document, queue_depth


def test_enqueue_document(monkeypatch):
    stored: list[str] = []

    class FakeRedis:
        def rpush(self, key, value):
            stored.append(value)

        def llen(self, key):
            return len(stored)

    monkeypatch.setattr(
        "backend.workers.indexing_queue.get_redis",
        lambda: FakeRedis(),
    )
    doc_id = uuid4()
    assert enqueue_document(doc_id) is True
    assert stored == [str(doc_id)]
    assert queue_depth() == 1
