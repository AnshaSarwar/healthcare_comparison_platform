"use client";

import { useCallback, useRef, useState } from "react";
import { ApiError, streamAgentChat } from "@/lib/api";
import type { AgentSseEvent, Citation, SourceChunk } from "@/lib/types";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps?: string[];
  sources?: SourceChunk[];
  citations?: Citation[];
  route?: string;
}

export type ConnectionState = "idle" | "streaming" | "error" | "disconnected";

interface UseAgentStreamResult {
  messages: ChatMessage[];
  sending: boolean;
  connectionState: ConnectionState;
  error: string | null;
  threadId: string | null;
  send: (question: string, planIds: string[]) => void;
  cancel: () => void;
}

/**
 * Consumes the agent chat SSE stream: splits the metadata-first "sources" event from
 * the token stream (they arrive as distinct SSE event types — see
 * backend/services/agent.py and backend/agents/nodes.py:generate_node), keeps "step"
 * and "final" handling, and tells "disconnected" (a genuine network drop) apart from
 * "error" (an HTTP-level failure) and a user-initiated cancel (silent, no error state)
 * so the UI can react differently to each. Does not auto-retry — a dropped connection
 * surfaces as state for the caller to act on, not a retry storm.
 */
export function useAgentStream(): UseAgentStreamResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [connectionState, setConnectionState] = useState<ConnectionState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const send = useCallback(
    (question: string, planIds: string[]) => {
      const text = question.trim();
      if (!text || sending) return;

      setError(null);
      setConnectionState("streaming");
      const userMsg: ChatMessage = { id: crypto.randomUUID(), role: "user", content: text };
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", steps: [] },
      ]);
      setSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      function onEvent(event: AgentSseEvent) {
        if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, sources: event.sources } : m)),
          );
        } else if (event.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + (event.text || "") } : m,
            ),
          );
        } else if (event.type === "step") {
          const label = `${event.node}: ${event.detail}`;
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId ? { ...m, steps: [...(m.steps || []), label] } : m,
            ),
          );
        } else if (event.type === "final") {
          if (event.thread_id) setThreadId(event.thread_id);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: event.answer || m.content, citations: event.citations, route: event.route }
                : m,
            ),
          );
        } else if (event.type === "error") {
          setError(event.detail);
          setConnectionState("error");
        }
      }

      streamAgentChat(
        { question: text, plan_ids: planIds, thread_id: threadId },
        onEvent,
        controller.signal,
      )
        .then(() => {
          if (!controller.signal.aborted) setConnectionState("idle");
        })
        .catch((err: unknown) => {
          if (err instanceof DOMException && err.name === "AbortError") {
            // User-initiated cancel — not an error state.
            setConnectionState("idle");
            return;
          }
          if (err instanceof ApiError) {
            setError(err.message);
            setConnectionState("error");
          } else {
            // fetch() throws a plain TypeError ("Failed to fetch"/"NetworkError…")
            // when the connection drops mid-stream or never opens — a genuinely
            // different situation from a server-returned error.
            setError("Connection lost. Check your network and try again.");
            setConnectionState("disconnected");
          }
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && !m.content
                ? { ...m, content: "Sorry — something went wrong." }
                : m,
            ),
          );
        })
        .finally(() => {
          setSending(false);
          abortRef.current = null;
        });
    },
    [sending, threadId],
  );

  return { messages, sending, connectionState, error, threadId, send, cancel };
}
