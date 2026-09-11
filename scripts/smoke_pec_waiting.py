"""Smoke the PEC waiting-period agent question (uses local demo credentials)."""

from __future__ import annotations

import json
import urllib.request

API = "http://127.0.0.1:8101/api/v1"


def _post_json(path: str, body: dict, token: str | None = None) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode())


def _get_json(path: str, token: str) -> list | dict:
    req = urllib.request.Request(
        f"{API}{path}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _stream_agent(token: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}/agents/chat",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
        },
        method="POST",
    )
    final: dict | None = None
    steps: list[str] = []
    tokens: list[str] = []
    with urllib.request.urlopen(req, timeout=180) as resp:
        buffer = ""
        while True:
            chunk = resp.read(1024)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            parts = buffer.split("\n\n")
            buffer = parts.pop()
            for part in parts:
                line = next((l[5:].strip() for l in part.split("\n") if l.startswith("data:")), "")
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "step":
                    steps.append(f"{event.get('node')}:{event.get('detail')}")
                if event.get("type") == "token":
                    tokens.append(str(event.get("text") or ""))
                if event.get("type") == "final":
                    final = event
    print("steps=", " | ".join(steps))
    print("streamed=", "".join(tokens))
    if final is None:
        raise RuntimeError("No final SSE event")
    return final


def main() -> None:
    token = _post_json("/auth/login", {"email": "employer@acme.com", "password": "password123"})[
        "access_token"
    ]
    plans = _get_json("/plans", token)
    assert isinstance(plans, list) and plans
    final = _stream_agent(
        token,
        {
            "question": "What is the waiting period for pre-existing conditions?",
            "plan_ids": [p["id"] for p in plans],
        },
    )
    answer = final.get("answer") or ""
    cites = final.get("citations") or []
    plan_names = {c.get("plan_name") for c in cites}
    print("route=", final.get("route"))
    print("citations=", len(cites), sorted(plan_names))
    print(answer)
    assert "12 months" in answer or "12-month" in answer.lower()
    assert "6 months" in answer or "six months" in answer.lower()
    assert any("Essential" in name for name in plan_names) or "not" in answer.lower()
    assert len(plan_names) >= 2
    assert "not premiums or pricing" not in answer.lower()


if __name__ == "__main__":
    main()
