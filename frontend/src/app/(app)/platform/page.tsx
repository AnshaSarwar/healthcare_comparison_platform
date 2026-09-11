"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  createOrganization,
  createUser,
  listOrganizations,
} from "@/lib/api";
import type { Organization, OrganizationType } from "@/lib/types";

export default function PlatformPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [profileName, setProfileName] = useState("");
  const [orgType, setOrgType] = useState<OrganizationType>("employer");
  const [userEmail, setUserEmail] = useState("");
  const [userPassword, setUserPassword] = useState("password123");
  const [userOrgId, setUserOrgId] = useState("");
  const [userRole, setUserRole] = useState("employer_admin");
  const [loading, setLoading] = useState(true);

  async function refresh() {
    const data = await listOrganizations();
    setOrgs(data);
    if (!userOrgId && data[0]) setUserOrgId(data[0].id);
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await listOrganizations();
        if (cancelled) return;
        setOrgs(data);
        if (data[0]) setUserOrgId(data[0].id);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load organizations");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onCreateOrg(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createOrganization({
        name: orgName,
        org_type: orgType,
        profile_name: profileName,
      });
      setOrgName("");
      setProfileName("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create org failed");
    }
  }

  async function onCreateUser(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createUser({
        email: userEmail,
        password: userPassword,
        role: userRole,
        organization_id: userOrgId,
      });
      setUserEmail("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create user failed");
    }
  }

  if (loading) return <p className="muted">Loading platform…</p>;

  return (
    <div>
      <h1 className="page-title">Platform admin</h1>
      <p className="page-lead">Manage tenants and users across the platform.</p>
      {error && <div className="error-banner">{error}</div>}

      <section className="panel" style={{ marginBottom: 18 }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Organizations</h2>
        <ul>
          {orgs.map((org) => (
            <li key={org.id}>
              <strong>{org.name}</strong> · {org.org_type} ·{" "}
              <span className="muted">{org.id.slice(0, 8)}…</span>
            </li>
          ))}
        </ul>
      </section>

      <form className="panel" onSubmit={onCreateOrg} style={{ marginBottom: 18 }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Create organization</h2>
        <div className="field">
          <label htmlFor="orgType">Type</label>
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
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="profileName">Profile name</label>
          <input
            id="profileName"
            value={profileName}
            onChange={(e) => setProfileName(e.target.value)}
            required
          />
        </div>
        <button className="btn" type="submit">
          Create
        </button>
      </form>

      <form className="panel" onSubmit={onCreateUser}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Create user</h2>
        <div className="field">
          <label htmlFor="userOrg">Organization</label>
          <select
            id="userOrg"
            value={userOrgId}
            onChange={(e) => setUserOrgId(e.target.value)}
            required
          >
            {orgs.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name} ({org.org_type})
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="userRole">Role</label>
          <select
            id="userRole"
            value={userRole}
            onChange={(e) => setUserRole(e.target.value)}
          >
            <option value="employer_admin">employer_admin</option>
            <option value="healthcare_org_admin">healthcare_org_admin</option>
            <option value="platform_admin">platform_admin</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="userEmail">Email</label>
          <input
            id="userEmail"
            type="email"
            value={userEmail}
            onChange={(e) => setUserEmail(e.target.value)}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="userPassword">Password</label>
          <input
            id="userPassword"
            type="password"
            minLength={8}
            value={userPassword}
            onChange={(e) => setUserPassword(e.target.value)}
            required
          />
        </div>
        <button className="btn" type="submit">
          Create user
        </button>
      </form>
    </div>
  );
}
