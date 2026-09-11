"use client";

import { FormEvent, useEffect, useState } from "react";
import PlanEditorForm, { type PlanEditorValues } from "@/components/PlanEditorForm";
import {
  ApiError,
  addHospital,
  createPlan,
  fetchDocumentContent,
  getProviderMe,
  listPlans,
  listPlanVersions,
  reviewPlanVersion,
  updatePlan,
} from "@/lib/api";
import type { Plan, PlanVersion, ProviderProfile } from "@/lib/types";

export default function ProviderPage() {
  const [provider, setProvider] = useState<ProviderProfile | null>(null);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [versions, setVersions] = useState<Record<string, PlanVersion[]>>({});
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [createKey, setCreateKey] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [hospitalName, setHospitalName] = useState("");
  const [hospitalCity, setHospitalCity] = useState("");
  const [hospitalTier, setHospitalTier] = useState("standard");
  const [loading, setLoading] = useState(true);

  const editingPlan = plans.find((plan) => plan.id === editingId) ?? null;

  async function refresh() {
    const [p, listed] = await Promise.all([getProviderMe(), listPlans()]);
    setProvider(p);
    const ownedPlans = listed.filter((item) => item.organization_id === p.organization_id);
    setPlans(ownedPlans);
    const versionEntries = await Promise.all(
      ownedPlans.map(async (plan) => [plan.id, await listPlanVersions(plan.id)] as const),
    );
    setVersions(Object.fromEntries(versionEntries));
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await refresh();
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load provider");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onCreatePlan(values: PlanEditorValues) {
    setError(null);
    setSaved(null);
    setSubmitting(true);
    try {
      await createPlan(values);
      setSaved("Plan created");
      setCreateKey((key) => key + 1);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Plan create failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function onUpdatePlan(values: PlanEditorValues) {
    if (!editingId) return;
    setError(null);
    setSaved(null);
    setSubmitting(true);
    try {
      await updatePlan(editingId, values);
      setSaved("Plan updated");
      setEditingId(null);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Plan update failed");
    } finally {
      setSubmitting(false);
    }
  }

  async function onAddHospital(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(null);
    try {
      await addHospital({
        name: hospitalName,
        city: hospitalCity,
        tier: hospitalTier,
      });
      setHospitalName("");
      setHospitalCity("");
      setHospitalTier("standard");
      setSaved("Hospital added");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Hospital create failed");
    }
  }

  async function onReviewVersion(
    versionId: string,
    reviewStatus: "approved" | "archived" | "needs_correction",
  ) {
    setError(null);
    setSaved(null);
    try {
      await reviewPlanVersion(versionId, reviewStatus, reviewNote.trim() || undefined);
      setSaved(`Version ${reviewStatus}`);
      setReviewNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Version review failed");
    }
  }

  async function onViewSource(documentId: string) {
    try {
      const blob = await fetchDocumentContent(documentId);
      window.open(URL.createObjectURL(blob), "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load source document");
    }
  }

  if (loading) return <p className="muted">Loading provider…</p>;

  return (
    <div>
      <h1 className="page-title">Provider workspace</h1>
      <p className="page-lead">
        {provider?.name} · {provider?.hospital_count ?? 0} hospitals in network. Edit coverage
        terms and pricing used by comparison and chat.
      </p>
      {error && <div className="error-banner">{error}</div>}
      {saved && <p className="chip">{saved}</p>}

      <section className="panel" style={{ marginBottom: 18 }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Your plans</h2>
        <ul className="plan-list">
          {plans.map((plan) => (
            <li key={plan.id} className="plan-list-item">
              <div>
                <strong>{plan.name}</strong>
                <div className="muted" style={{ fontSize: "0.92rem" }}>
                  {plan.coverage_type} · wait {plan.terms.waiting_period_days}d ·{" "}
                  {plan.pricing_tiers.length} pricing tier
                  {plan.pricing_tiers.length === 1 ? "" : "s"} · {plan.network_hospital_count}{" "}
                  hospitals
                </div>
                {(versions[plan.id] ?? []).length > 0 && (
                  <div className="muted" style={{ marginTop: 8, fontSize: "0.85rem" }}>
                    {(versions[plan.id] ?? []).map((version) => (
                      <div key={version.id} style={{ marginTop: 4 }}>
                        <span className={`chip ${version.review_status}`}>
                          {version.review_status}
                        </span>{" "}
                        {version.version_label}
                        {version.imported_by_role && (
                          <span className="muted" style={{ marginLeft: 8, fontSize: "0.8rem" }}>
                            {version.imported_by_role === "healthcare_org_admin"
                              ? "· uploaded by provider"
                              : version.imported_by_role === "employer_admin"
                                ? "· imported by employer"
                                : "· imported by platform"}
                          </span>
                        )}
                        {version.source_document_id && (
                          <button
                            type="button"
                            className="btn btn-secondary"
                            style={{ padding: "4px 8px", fontSize: "0.75rem", marginLeft: 8 }}
                            onClick={() => onViewSource(version.source_document_id as string)}
                          >
                            View source
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-secondary"
                          style={{ padding: "4px 8px", fontSize: "0.75rem", marginLeft: 8 }}
                          onClick={() =>
                            setExpandedVersion((current) =>
                              current === version.id ? null : version.id,
                            )
                          }
                        >
                          {expandedVersion === version.id ? "Hide terms" : "Review terms"}
                        </button>
                        {expandedVersion === version.id && (
                          <div style={{ margin: "8px 0 0" }}>
                            <label className="field">
                              <span>Reviewer note</span>
                              <textarea
                                rows={2}
                                value={reviewNote}
                                onChange={(event) => setReviewNote(event.target.value)}
                                placeholder="Explain any correction needed or approval context"
                              />
                            </label>
                            <strong>Normalized terms</strong>
                            <pre style={{ whiteSpace: "pre-wrap", margin: "4px 0 8px" }}>
                              {JSON.stringify(version.normalized_terms, null, 2)}
                            </pre>
                            <strong>Extraction evidence</strong>
                            {(version.extraction_metadata.evidence ?? []).map((item) => (
                              <div key={item.field} style={{ marginTop: 6 }}>
                                <div>
                                  {item.field}: {String(item.value)} · confidence {item.confidence}
                                </div>
                                <q>{item.quote}</q>
                              </div>
                            ))}
                          </div>
                        )}
                        {version.review_status === "needs_review" && (
                          <span className="actions" style={{ display: "inline-flex", marginLeft: 8 }}>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                              onClick={() => onReviewVersion(version.id, "approved")}
                            >
                              Approve
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                              onClick={() => onReviewVersion(version.id, "archived")}
                            >
                              Archive
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary"
                              style={{ padding: "4px 8px", fontSize: "0.75rem" }}
                              onClick={() => onReviewVersion(version.id, "needs_correction")}
                            >
                              Request correction
                            </button>
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setSaved(null);
                  setEditingId(plan.id);
                }}
              >
                Edit
              </button>
            </li>
          ))}
          {plans.length === 0 && <li className="muted">No plans yet</li>}
        </ul>
      </section>

      {editingPlan ? (
        <div style={{ marginBottom: 18 }}>
          <PlanEditorForm
            mode="edit"
            initialPlan={editingPlan}
            submitting={submitting}
            onSubmit={onUpdatePlan}
            onCancel={() => setEditingId(null)}
          />
        </div>
      ) : (
        <div style={{ marginBottom: 18 }}>
          <PlanEditorForm
            key={createKey}
            mode="create"
            submitting={submitting}
            onSubmit={onCreatePlan}
          />
        </div>
      )}

      <form className="panel" onSubmit={onAddHospital}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Add hospital</h2>
        <div className="form-grid">
          <div className="field">
            <label htmlFor="hName">Name</label>
            <input
              id="hName"
              value={hospitalName}
              onChange={(e) => setHospitalName(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="hCity">City</label>
            <input
              id="hCity"
              value={hospitalCity}
              onChange={(e) => setHospitalCity(e.target.value)}
              required
            />
          </div>
          <div className="field">
            <label htmlFor="hTier">Tier</label>
            <select
              id="hTier"
              value={hospitalTier}
              onChange={(e) => setHospitalTier(e.target.value)}
            >
              <option value="standard">Standard</option>
              <option value="preferred">Preferred</option>
              <option value="tertiary">Tertiary</option>
            </select>
          </div>
        </div>
        <button className="btn" type="submit">
          Add to network
        </button>
      </form>
    </div>
  );
}
