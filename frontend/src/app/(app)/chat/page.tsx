"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, listPlans } from "@/lib/api";
import { useAgentStream } from "@/lib/hooks/useAgentStream";
import type { Plan } from "@/lib/types";

const SELECTED_KEY = "benefits_selected_plans";

export default function ChatPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planIds, setPlanIds] = useState<string[]>([]);
  const [question, setQuestion] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const logRef = useRef<HTMLDivElement>(null);

  const { messages, sending, connectionState, error, send, cancel } = useAgentStream();

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
          setLoadError(err instanceof ApiError ? err.message : "Failed to load plans");
        }
      }
    })();
    return () => {
      cancelled = true;
      cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!question.trim() || sending) return;
    send(question, planIds);
    setQuestion("");
  }

  function togglePlan(id: string) {
    setPlanIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  const banner = loadError || error;

  return (
    <div className="chat-layout">
      <div>
        <h1 className="page-title">Benefits assistant</h1>
        <p className="page-lead">
          Ask policy questions or request a comparison. Answers stream live with
          citations when documents are indexed.
        </p>
        {banner && <div className="error-banner">{banner}</div>}
        {connectionState === "disconnected" && (
          <div className="error-banner">
            Connection dropped mid-answer. Check your network, then send the question
            again.
          </div>
        )}
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
            {m.role === "assistant" && m.sources && m.sources.length > 0 && (
              <div className="plan-meta" style={{ marginBottom: 6 }}>
                {m.sources.map((s) => (
                  <span key={s.index} className="chip" title={s.section || undefined}>
                    [{s.index}] {s.plan_name}
                    {s.page_number != null ? ` · p.${s.page_number}` : ""}
                  </span>
                ))}
              </div>
            )}
            <div style={{ whiteSpace: "pre-wrap" }}>
              {m.content || (sending ? "…" : "")}
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
                    {c.page_number != null ? ` (p.${c.page_number})` : ""}
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
          disabled={sending || planIds.length === 0}
        />
        <button
          className="btn"
          type="submit"
          disabled={sending || !question.trim() || planIds.length === 0}
        >
          {sending ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
