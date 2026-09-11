"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, listPlans, streamAgentChat } from "@/lib/api";
import type { Citation, Plan } from "@/lib/types";

const SELECTED_KEY = "benefits_selected_plans";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  steps?: string[];
  citations?: Citation[];
  route?: string;
}

export default function ChatPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planIds, setPlanIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listPlans();
        if (cancelled) return;
        setPlans(data);
        const saved = localStorage.getItem(SELECTED_KEY);
        if (saved) {
          const ids = JSON.parse(saved) as string[];
          const valid = ids.filter((id) => data.some((p) => p.id === id));
          setPlanIds(valid.length ? valid : data.map((p) => p.id));
        } else {
          setPlanIds(data.map((p) => p.id));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load plans");
        }
      }
    })();
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const text = question.trim();
    if (!text || streaming) return;

    setError(null);
    setQuestion("");
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
    };
    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", content: "", steps: [] },
    ]);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamAgentChat(
        { question: text, plan_ids: planIds, thread_id: threadId },
        (event) => {
          if (event.type === "token") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: m.content + (event.text || "") }
                  : m,
              ),
            );
          } else if (event.type === "step") {
            const label = `${event.node}: ${event.detail}`;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, steps: [...(m.steps || []), label] }
                  : m,
              ),
            );
          } else if (event.type === "final") {
            if (event.thread_id) setThreadId(event.thread_id);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      content: event.answer || m.content,
                      citations: event.citations,
                      route: event.route,
                    }
                  : m,
              ),
            );
          } else if (event.type === "error") {
            setError(event.detail);
          }
        },
        controller.signal,
      );
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        setError(err instanceof ApiError ? err.message : "Chat failed");
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId && !m.content
              ? { ...m, content: "Sorry — something went wrong." }
              : m,
          ),
        );
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
    }
  }

  function togglePlan(id: string) {
    setPlanIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  return (
    <div className="chat-layout">
      <div>
        <h1 className="page-title">Benefits assistant</h1>
        <p className="page-lead">
          Ask policy questions or request a comparison. Answers stream live with
          citations when documents are indexed.
        </p>
        {error && <div className="error-banner">{error}</div>}
        <div className="panel" style={{ marginBottom: 8 }}>
          <p style={{ margin: "0 0 10px", fontWeight: 600, fontSize: "0.9rem" }}>
            Scope to plans
          </p>
          <div className="plan-meta">
            {plans.map((plan) => (
              <label key={plan.id} className="chip" style={{ cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={planIds.includes(plan.id)}
                  onChange={() => togglePlan(plan.id)}
                  style={{ marginRight: 6 }}
                />
                {plan.name}
              </label>
            ))}
          </div>
        </div>
      </div>

      <div className="chat-log panel" ref={logRef}>
        {messages.length === 0 && (
          <p className="muted" style={{ margin: 0 }}>
            Try: “Compare these plans for maternity and budget fit” or “What is
            the waiting period for pre-existing conditions?”
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}`}>
            {m.role === "assistant" && m.steps && m.steps.length > 0 && (
              <div className="steps">{m.steps.join(" → ")}</div>
            )}
            <div style={{ whiteSpace: "pre-wrap" }}>
              {m.content || (streaming ? "…" : "")}
            </div>
            {m.route && (
              <div className="muted" style={{ marginTop: 8, fontSize: "0.75rem" }}>
                Route: {m.route}
              </div>
            )}
            {m.citations && m.citations.length > 0 && (
              <div className="citations">
                {m.citations.map((c, i) => (
                  <blockquote key={`${c.document_id}-${i}`} className="citation">
                    <strong>{c.plan_name}</strong> — {c.section}
                    <div style={{ marginTop: 4 }}>&ldquo;{c.quote}&rdquo;</div>
                  </blockquote>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <form className="chat-composer" onSubmit={onSubmit}>
        <textarea
          rows={2}
          placeholder="Ask about coverage, waiting periods, or compare plans…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={streaming || planIds.length === 0}
        />
        <button
          className="btn"
          type="submit"
          disabled={streaming || !question.trim() || planIds.length === 0}
        >
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
