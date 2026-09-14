"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ApiError, getComparison } from "@/lib/api";
import type { ComparisonRequest, PlanEligibilityResult } from "@/lib/types";

export default function ComparisonDetailPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<ComparisonRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const result = await getComparison(params.id);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load comparison");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [params.id]);

  const ranked = useMemo(() => {
    if (!data?.result) return [];
    const byId = new Map(
      data.result.eligibility_matrix.map((row) => [row.plan_id, row]),
    );
    return data.result.scored_ranking
      .map((id) => byId.get(id))
      .filter((row): row is PlanEligibilityResult => Boolean(row));
  }, [data]);

  const brandSummaries = useMemo(() => {
    const groups = new Map<string, PlanEligibilityResult[]>();
    for (const row of ranked) {
      const group = groups.get(row.provider_name) ?? [];
      group.push(row);
      groups.set(row.provider_name, group);
    }
    return [...groups.entries()].map(([brand, rows]) => ({
      brand,
      totalPlans: rows.length,
      qualifyingPlans: rows.filter((row) => row.overall_outcome === "pass").length,
      bestPlan: rows.find((row) => row.overall_outcome === "pass") ?? rows[0],
    }));
  }, [ranked]);

  function toggleRules(planId: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(planId)) next.delete(planId);
      else next.add(planId);
      return next;
    });
  }

  if (loading) {
    return <p className="muted">Loading comparison…</p>;
  }

  if (error || !data) {
    return (
      <div>
        <div className="error-banner">{error || "Comparison not found"}</div>
        <Link href="/plans" className="btn btn-secondary">
          Back to plans
        </Link>
      </div>
    );
  }

  const result = data.result;

  return (
    <div>
      <h1 className="page-title">Comparison</h1>
      <p className="page-lead">
        Status: <strong>{data.status}</strong>
        {" · "}
        {data.plan_ids.length} plans evaluated
      </p>

      <div className="actions" style={{ marginBottom: 20 }}>
        <Link href="/plans" className="btn btn-secondary">
          Back to plans
        </Link>
        <Link href="/chat" className="btn">
          Ask about these plans
        </Link>
      </div>

      {!result ? (
        <div className="panel">
          <p className="muted">No result payload yet for this request.</p>
        </div>
      ) : (
        <>
          <section className="panel" style={{ marginBottom: 18 }}>
            <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>
              Brand summary
            </h2>
            <div className="plan-list">
              {brandSummaries.map((summary) => (
                <div key={summary.brand} className="plan-list-item">
                  <div>
                    <strong>{summary.brand}</strong>
                    <div className="muted">
                      {summary.qualifyingPlans} of {summary.totalPlans} plans meet all requirements
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className={`outcome ${summary.bestPlan.overall_outcome}`}>
                      {summary.bestPlan.overall_outcome}
                    </div>
                    <div className="muted" style={{ fontSize: "0.85rem" }}>
                      Best: {summary.bestPlan.plan_name}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <section className="panel" style={{ marginBottom: 18 }}>
            <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>
              Ranked results
            </h2>
            <table className="rank-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Plan</th>
                  <th>Outcome</th>
                  <th>Score</th>
                  <th>Est. monthly</th>
                  <th>Rules</th>
                </tr>
              </thead>
              <tbody>
                {ranked.map((row, index) => (
                  <tr key={row.plan_id}>
                    <td>{index + 1}</td>
                    <td>
                      <div className="muted" style={{ fontSize: "0.8rem" }}>
                        {row.provider_name}
                      </div>
                      <strong>{row.plan_name}</strong>
                      {row.score_breakdown && (
                        <div className="muted" style={{ fontSize: "0.8rem" }}>
                          cost {(row.score_breakdown.cost ?? 0).toFixed(2)} · coverage{" "}
                          {(row.score_breakdown.coverage ?? 0).toFixed(2)} · network{" "}
                          {(row.score_breakdown.network ?? 0).toFixed(2)}
                        </div>
                      )}
                    </td>
                    <td>
                      <span className={`outcome ${row.overall_outcome}`}>
                        {row.overall_outcome}
                      </span>
                    </td>
                    <td>{row.total_score != null ? row.total_score.toFixed(3) : "—"}</td>
                    <td>
                      {row.estimated_monthly_cost != null
                        ? `$${row.estimated_monthly_cost.toLocaleString()}`
                        : "—"}
                    </td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ padding: "6px 10px", fontSize: "0.8rem" }}
                        onClick={() => toggleRules(row.plan_id)}
                      >
                        {expanded.has(row.plan_id) ? "Hide" : "Show"}
                      </button>
                      {expanded.has(row.plan_id) && (
                        <ul className="rules">
                          {row.rules.map((rule) => (
                            <li key={rule.rule_id}>
                              <strong>{rule.rule_name}</strong> ({rule.outcome}):{" "}
                              {rule.message}
                            </li>
                          ))}
                        </ul>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {result.narrative_explanation && (
            <section className="panel" style={{ marginBottom: 18 }}>
              <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>
                Narrative
              </h2>
              <p className="narrative">{result.narrative_explanation}</p>
            </section>
          )}

          {(result.citations?.length ?? 0) > 0 && (
            <section className="panel">
              <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>
                Citations
              </h2>
              <div className="citations">
                {result.citations!.map((c, i) => (
                  <blockquote key={`${c.document_id}-${i}`} className="citation">
                    <strong>{c.plan_name}</strong> — {c.section}
                    <div style={{ marginTop: 4 }}>&ldquo;{c.quote}&rdquo;</div>
                  </blockquote>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
