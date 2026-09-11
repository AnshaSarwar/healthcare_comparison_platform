from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("benefits.agent")


def log_agent_event(node: str, detail: str, **fields: Any) -> None:
    payload = {"event": "agent_node", "node": node, "detail": detail, **fields}
    logger.info(json.dumps(payload, default=str))
