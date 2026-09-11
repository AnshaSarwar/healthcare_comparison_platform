"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createComparison, listPlans } from "@/lib/api";
import type { Plan } from "@/lib/types";

const SELECTED_KEY = "benefits_selected_plans";

function coverageLabel(type: Plan["coverage_type"]): string {
  if (type === "opd_ipd") return "OPD + IPD";
  return type.toUpperCase();
}

export default function PlansPage() {
  const router = useRouter();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [comparing, setComparing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listPlans();
        if (cancelled) return;
        setPlans(data);
        const saved = localStorage.getItem(SELECTED_KEY);
        if (saved) {
          const ids = new Set<string>(JSON.parse(saved) as string[]);
          setSelected(new Set(data.filter((p) => ids.has(p.id)).map((p) => p.id)));
        } else {
          setSelected(new Set(data.map((p) => p.id)));
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load plans");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    localStorage.setItem(SELECTED_KEY, JSON.stringify([...selected]));
  }, [selected]);

  const selectedCount = selected.size;
  const allSelected = useMemo(
    () => plans.length > 0 && selected.size === plans.length,
    [plans, selected],
  );
  const plansByBrand = useMemo(() => {
    const groups = new Map<string, Plan[]>();
    for (const plan of plans) {
      const group = groups.get(plan.provider_name) ?? [];
      group.push(plan);
      groups.set(plan.provider_name, group);
    }
    return [...groups.entries()];
  }, [plans]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(plans.map((p) => p.id)));
  }

  function toggleBrand(brandPlans: Plan[]) {
    const brandIds = brandPlans.map((plan) => plan.id);
    const brandSelected = brandIds.every((id) => selected.has(id));
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of brandIds) {
        if (brandSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  async function runCompare() {
    if (selected.size === 0) return;
    setComparing(true);
    setError(null);
    try {
      const result = await createComparison([...selected]);
      router.push(`/comparisons/${result.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Comparison failed");
    } finally {
      setComparing(false);
    }
  }

  function goChat() {
    router.push("/chat");
  }

  return (
    <div>
      <h1 className="page-title">Plans</h1>
      <p className="page-lead">
        Compare provider brands through their available plans, then run a
        rules-based comparison or ask the benefits assistant.
      </p>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <p className="muted">Loading plans…</p>
      ) : (
        <>
          <div className="actions" style={{ marginBottom: 16 }}>
            <button type="button" className="btn-secondary btn" onClick={toggleAll}>
              {allSelected ? "Clear selection" : "Select all"}
            </button>
            <span className="muted">{selectedCount} selected</span>
          </div>

          <div className="plan-list">
            {plansByBrand.map(([brand, brandPlans]) => (
              <section key={brand} className="panel">
                <div className="actions" style={{ justifyContent: "space-between" }}>
                  <div>
                    <h2 style={{ margin: 0, fontFamily: "var(--font-display)" }}>{brand}</h2>
                    <p className="muted" style={{ margin: "4px 0 0" }}>
                      {brandPlans.length} {brandPlans.length === 1 ? "plan" : "plans"} available
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => toggleBrand(brandPlans)}
                  >
                    {brandPlans.every((plan) => selected.has(plan.id))
                      ? "Clear brand"
                      : "Select brand"}
                  </button>
                </div>
                {brandPlans.map((plan) => (
                  <label key={plan.id} className="plan-row">
                    <input
                      type="checkbox"
                      checked={selected.has(plan.id)}
                      onChange={() => toggle(plan.id)}
                    />
                    <div>
                      <h3>{plan.name}</h3>
                      <p className="muted" style={{ margin: 0, fontSize: "0.9rem" }}>
                        Maternity {plan.terms.maternity_coverage ? "covered" : "not covered"}
                        {" · "}
                        Waiting period {plan.terms.waiting_period_days} days
                      </p>
                      <div className="plan-meta">
                        <span className="chip">{coverageLabel(plan.coverage_type)}</span>
                        <span className="chip">
                          {plan.network_hospital_count} network hospitals
                        </span>
                        <span className="chip">
                          Min {plan.terms.min_employee_count} employees
                        </span>
                      </div>
                    </div>
                  </label>
                ))}
              </section>
            ))}
          </div>

          <div className="actions">
            <button
              type="button"
              className="btn"
              disabled={selectedCount === 0 || comparing}
              onClick={runCompare}
            >
              {comparing ? "Comparing…" : "Compare selected"}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={selectedCount === 0}
              onClick={goChat}
            >
              Ask assistant
            </button>
          </div>
        </>
      )}
    </div>
  );
}
