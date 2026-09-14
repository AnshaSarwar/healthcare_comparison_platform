"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ApiError, fetchMe, register as registerApi } from "@/lib/api";
import { homeForRole, setMe } from "@/lib/auth";
import type { OrganizationType } from "@/lib/types";

export default function RegisterPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [profileName, setProfileName] = useState("");
  const [orgType, setOrgType] = useState<OrganizationType>("employer");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await registerApi({
        email,
        password,
        organization_name: organizationName,
        org_type: orgType,
        profile_name: profileName,
      });
      const me = await fetchMe();
      setMe(me);
      router.replace(homeForRole(me.role));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <form className="panel login-card" onSubmit={onSubmit} style={{ width: "min(480px, 100%)" }}>
        <h1>Register organization</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Creates your organization, profile, and first admin user.
        </p>
        {error && <div className="error-banner">{error}</div>}
        <div className="field">
          <label htmlFor="orgType">Organization type</label>
          <select
            id="orgType"
            value={orgType}
            onChange={(e) => setOrgType(e.target.value as OrganizationType)}
          >
            <option value="employer">Employer</option>
            <option value="healthcare_provider">Healthcare provider</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="orgName">Organization name</label>
          <input
            id="orgName"
            value={organizationName}
            onChange={(e) => setOrganizationName(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="profileName">Profile / display name</label>
          <input
            id="profileName"
            value={profileName}
            onChange={(e) => setProfileName(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="email">Admin email</label>
          <input
            id="email"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="password">Password (min 8)</label>
          <input
            id="password"
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button className="btn" type="submit" disabled={loading}>
          {loading ? "Creating…" : "Create account"}
        </button>
        <p className="hint">
          Already registered? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}
