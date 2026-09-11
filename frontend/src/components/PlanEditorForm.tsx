"use client";

import { FormEvent, useEffect, useState } from "react";
import type { CoverageType, Plan, PlanTerms, PricingTier } from "@/lib/types";

export type PlanEditorValues = {
  name: string;
  coverage_type: CoverageType;
  terms: PlanTerms;
  pricing_tiers: PricingTier[];
};

type SubLimitRow = { key: string; value: string };
type TierRow = { age_band_label: string; premium: string };

const EMPTY_TERMS: PlanTerms = {
  waiting_period_days: 30,
  exclusions: [],
  sub_limits: {},
  maternity_coverage: true,
  maternity_waiting_days: 180,
  pre_existing_condition_rules: "Covered after waiting period",
  min_employee_count: 10,
};

const DEFAULT_TIERS: TierRow[] = [
  { age_band_label: "18-35", premium: "300" },
  { age_band_label: "36-50", premium: "420" },
];

function parseNonNegInt(raw: string, fallback: number): number {
  const trimmed = raw.trim();
  if (trimmed === "") return fallback;
  const n = Number(trimmed);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return Math.floor(n);
}

function subLimitRowsFromTerms(terms: PlanTerms): SubLimitRow[] {
  const entries = Object.entries(terms.sub_limits || {});
  if (entries.length === 0) return [{ key: "", value: "" }];
  return entries.map(([key, value]) => ({ key, value: String(value) }));
}

function tiersFromPlan(plan: Plan): TierRow[] {
  if (plan.pricing_tiers.length === 0) {
    return DEFAULT_TIERS.map((tier) => ({ ...tier }));
  }
  return plan.pricing_tiers.map((tier) => ({
    age_band_label: tier.age_band_label,
    premium: String(tier.monthly_premium_per_employee),
  }));
}

function buildTerms(
  base: {
    waiting_period_days: string;
    min_employee_count: string;
    maternity_coverage: boolean;
    maternity_waiting_days: string;
    pre_existing_condition_rules: string;
  },
  exclusionsText: string,
  subLimitRows: SubLimitRow[],
): PlanTerms {
  const exclusions = exclusionsText
    .split(/\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  const sub_limits: Record<string, number> = {};
  for (const row of subLimitRows) {
    const key = row.key.trim();
    if (!key) continue;
    const amount = Number(row.value);
    if (!Number.isFinite(amount) || amount < 0) continue;
    sub_limits[key] = amount;
  }
  return {
    waiting_period_days: parseNonNegInt(base.waiting_period_days, 0),
    exclusions,
    sub_limits,
    maternity_coverage: base.maternity_coverage,
    maternity_waiting_days: parseNonNegInt(base.maternity_waiting_days, 0),
    pre_existing_condition_rules: base.pre_existing_condition_rules,
    min_employee_count: Math.max(1, parseNonNegInt(base.min_employee_count, 1)),
  };
}

type Props = {
  mode: "create" | "edit";
  initialPlan?: Plan | null;
  submitting?: boolean;
  onSubmit: (values: PlanEditorValues) => Promise<void> | void;
  onCancel?: () => void;
};

export default function PlanEditorForm({
  mode,
  initialPlan,
  submitting = false,
  onSubmit,
  onCancel,
}: Props) {
  const [name, setName] = useState("");
  const [coverageType, setCoverageType] = useState<CoverageType>("opd_ipd");
  const [waitingDays, setWaitingDays] = useState("30");
  const [minEmployees, setMinEmployees] = useState("10");
  const [maternityCoverage, setMaternityCoverage] = useState(true);
  const [maternityWait, setMaternityWait] = useState("180");
  const [pecRules, setPecRules] = useState("Covered after waiting period");
  const [exclusionsText, setExclusionsText] = useState("");
  const [subLimitRows, setSubLimitRows] = useState<SubLimitRow[]>([{ key: "", value: "" }]);
  const [tiers, setTiers] = useState<TierRow[]>(DEFAULT_TIERS.map((t) => ({ ...t })));
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (initialPlan) {
      const terms = { ...EMPTY_TERMS, ...initialPlan.terms };
      setName(initialPlan.name);
      setCoverageType(initialPlan.coverage_type);
      setWaitingDays(String(terms.waiting_period_days));
      setMinEmployees(String(terms.min_employee_count));
      setMaternityCoverage(terms.maternity_coverage);
      setMaternityWait(String(terms.maternity_waiting_days));
      setPecRules(terms.pre_existing_condition_rules || "");
      setExclusionsText((terms.exclusions || []).join("\n"));
      setSubLimitRows(subLimitRowsFromTerms(terms));
      setTiers(tiersFromPlan(initialPlan));
    } else {
      setName("");
      setCoverageType("opd_ipd");
      setWaitingDays(String(EMPTY_TERMS.waiting_period_days));
      setMinEmployees(String(EMPTY_TERMS.min_employee_count));
      setMaternityCoverage(EMPTY_TERMS.maternity_coverage);
      setMaternityWait(String(EMPTY_TERMS.maternity_waiting_days));
      setPecRules(EMPTY_TERMS.pre_existing_condition_rules);
      setExclusionsText("");
      setSubLimitRows([{ key: "", value: "" }]);
      setTiers(DEFAULT_TIERS.map((t) => ({ ...t })));
    }
    setFormError(null);
  }, [initialPlan, mode]);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormError(null);

    const cleanedTiers: PricingTier[] = [];
    for (const tier of tiers) {
      const label = tier.age_band_label.trim();
      if (!label) continue;
      const premium = Number(tier.premium);
      if (!Number.isFinite(premium) || premium < 0) {
        setFormError(`Invalid premium for age band "${label}"`);
        return;
      }
      cleanedTiers.push({
        age_band_label: label,
        monthly_premium_per_employee: premium,
      });
    }
    if (cleanedTiers.length === 0) {
      setFormError("Add at least one pricing tier with an age band and premium");
      return;
    }

    const trimmedName = name.trim();
    if (!trimmedName) {
      setFormError("Plan name is required");
      return;
    }

    await onSubmit({
      name: trimmedName,
      coverage_type: coverageType,
      terms: buildTerms(
        {
          waiting_period_days: waitingDays,
          min_employee_count: minEmployees,
          maternity_coverage: maternityCoverage,
          maternity_waiting_days: maternityWait,
          pre_existing_condition_rules: pecRules,
        },
        exclusionsText,
        subLimitRows,
      ),
      pricing_tiers: cleanedTiers,
    });
  }

  return (
    <form className="panel" onSubmit={handleSubmit}>
      <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>
        {mode === "create" ? "Create plan" : `Edit plan · ${initialPlan?.name ?? ""}`}
      </h2>
      {formError && <div className="error-banner">{formError}</div>}

      <div className="form-grid">
        <div className="field">
          <label htmlFor="plan-name">Plan name</label>
          <input
            id="plan-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="coverage-type">Coverage type</label>
          <select
            id="coverage-type"
            value={coverageType}
            onChange={(e) => setCoverageType(e.target.value as CoverageType)}
          >
            <option value="opd">OPD</option>
            <option value="ipd">IPD</option>
            <option value="opd_ipd">OPD + IPD</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="waiting-days">Waiting period (days)</label>
          <input
            id="waiting-days"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={waitingDays}
            onChange={(e) => setWaitingDays(e.target.value.replace(/[^\d]/g, ""))}
            placeholder="e.g. 45"
            required
          />
        </div>
        <div className="field">
          <label htmlFor="min-employees">Min employee count</label>
          <input
            id="min-employees"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={minEmployees}
            onChange={(e) => setMinEmployees(e.target.value.replace(/[^\d]/g, ""))}
            placeholder="e.g. 10"
            required
          />
        </div>
      </div>

      <label className="field" style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
        <input
          type="checkbox"
          checked={maternityCoverage}
          onChange={(e) => setMaternityCoverage(e.target.checked)}
        />
        Maternity coverage included
      </label>

      <div className="form-grid">
        <div className="field">
          <label htmlFor="maternity-wait">Maternity waiting (days)</label>
          <input
            id="maternity-wait"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            value={maternityWait}
            onChange={(e) => setMaternityWait(e.target.value.replace(/[^\d]/g, ""))}
            disabled={!maternityCoverage}
            placeholder="e.g. 180"
          />
        </div>
        <div className="field">
          <label htmlFor="pec-rules">Pre-existing condition rules</label>
          <input
            id="pec-rules"
            value={pecRules}
            onChange={(e) => setPecRules(e.target.value)}
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="exclusions">Exclusions (one per line or comma-separated)</label>
        <textarea
          id="exclusions"
          rows={3}
          value={exclusionsText}
          onChange={(e) => setExclusionsText(e.target.value)}
          placeholder={"cosmetic surgery\nexperimental treatment"}
        />
      </div>

      <div className="field">
        <span className="field-heading">Sub-limits</span>
        {subLimitRows.map((row, index) => (
          <div className="inline-row" key={`sub-${index}`}>
            <input
              aria-label={`Sub-limit category ${index + 1}`}
              placeholder="Category (e.g. dental)"
              value={row.key}
              onChange={(e) =>
                setSubLimitRows((prev) =>
                  prev.map((item, i) => (i === index ? { ...item, key: e.target.value } : item)),
                )
              }
            />
            <input
              aria-label={`Sub-limit amount ${index + 1}`}
              type="text"
              inputMode="numeric"
              placeholder="Amount"
              value={row.value}
              onChange={(e) =>
                setSubLimitRows((prev) =>
                  prev.map((item, i) =>
                    i === index
                      ? { ...item, value: e.target.value.replace(/[^\d.]/g, "") }
                      : item,
                  ),
                )
              }
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() =>
                setSubLimitRows((prev) =>
                  prev.length <= 1 ? [{ key: "", value: "" }] : prev.filter((_, i) => i !== index),
                )
              }
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setSubLimitRows((prev) => [...prev, { key: "", value: "" }])}
        >
          Add sub-limit
        </button>
      </div>

      <div className="field">
        <span className="field-heading">Pricing tiers</span>
        {tiers.map((tier, index) => (
          <div className="inline-row" key={`tier-${index}`}>
            <input
              aria-label={`Age band ${index + 1}`}
              placeholder="Age band (e.g. 25-34)"
              value={tier.age_band_label}
              onChange={(e) =>
                setTiers((prev) =>
                  prev.map((item, i) =>
                    i === index ? { ...item, age_band_label: e.target.value } : item,
                  ),
                )
              }
              required
            />
            <input
              aria-label={`Premium ${index + 1}`}
              type="text"
              inputMode="decimal"
              placeholder="Monthly premium / employee"
              value={tier.premium}
              onChange={(e) =>
                setTiers((prev) =>
                  prev.map((item, i) =>
                    i === index
                      ? { ...item, premium: e.target.value.replace(/[^\d.]/g, "") }
                      : item,
                  ),
                )
              }
              required
            />
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() =>
                setTiers((prev) =>
                  prev.length <= 1
                    ? [{ age_band_label: "", premium: "" }]
                    : prev.filter((_, i) => i !== index),
                )
              }
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setTiers((prev) => [...prev, { age_band_label: "", premium: "" }])}
        >
          Add pricing tier
        </button>
      </div>

      <div className="form-actions">
        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? "Saving…" : mode === "create" ? "Create plan" : "Save changes"}
        </button>
        {mode === "edit" && onCancel && (
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={submitting}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
