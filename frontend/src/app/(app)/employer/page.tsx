"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, getEmployerMe, updateEmployerMe } from "@/lib/api";
import type { EmployerProfile } from "@/lib/types";

export default function EmployerPage() {
  const [profile, setProfile] = useState<EmployerProfile | null>(null);
  const [name, setName] = useState("");
  const [budget, setBudget] = useState(500);
  const [maternity, setMaternity] = useState(false);
  const [preExisting, setPreExisting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getEmployerMe();
        if (cancelled) return;
        setProfile(data);
        setName(data.name);
        setBudget(data.requirements.budget_ceiling_per_employee);
        setMaternity(data.requirements.maternity_required);
        setPreExisting(data.requirements.pre_existing_coverage_required);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load employer");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setError(null);
    setSaved(false);
    try {
      const updated = await updateEmployerMe({
        name,
        requirements: {
          ...profile.requirements,
          budget_ceiling_per_employee: budget,
          maternity_required: maternity,
          pre_existing_coverage_required: preExisting,
        },
      });
      setProfile(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  if (loading) return <p className="muted">Loading employer profile…</p>;

  return (
    <div>
      <h1 className="page-title">Employer profile</h1>
      <p className="page-lead">Update requirements used by the comparison rules engine.</p>
      {error && <div className="error-banner">{error}</div>}
      {saved && <p className="chip">Saved</p>}
      <form className="panel" onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="name">Employer name</label>
          <input id="name" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label htmlFor="budget">Budget ceiling per employee</label>
          <input
            id="budget"
            type="number"
            min={1}
            step="1"
            value={budget}
            onChange={(e) => setBudget(Number(e.target.value))}
            required
          />
        </div>
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <input
            type="checkbox"
            checked={maternity}
            onChange={(e) => setMaternity(e.target.checked)}
          />
          Maternity required
        </label>
        <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <input
            type="checkbox"
            checked={preExisting}
            onChange={(e) => setPreExisting(e.target.checked)}
          />
          Pre-existing coverage required
        </label>
        <button className="btn" type="submit">
          Save
        </button>
      </form>
    </div>
  );
}
