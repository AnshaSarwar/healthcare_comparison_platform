from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver

_checkpointer = MemorySaver()


def get_checkpointer() -> MemorySaver:
    """In-process checkpoint for a single graph run / local multi-turn.

    Cross-restart thread history is stored in Redis via thread_store (messages).
    """
    return _checkpointer
