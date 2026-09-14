"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  ApiError,
  createInvite,
  createOrganization,
  createUser,
  listInvites,
  listOrganizations,
  revokeInvite,
} from "@/lib/api";
import type { Organization, OrganizationType, ProviderInvite } from "@/lib/types";

export default function PlatformPage() {
  const [orgs, setOrgs] = useState<Organization[]>([]);
  const [invites, setInvites] = useState<ProviderInvite[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [orgName, setOrgName] = useState("");
  const [profileName, setProfileName] = useState("");
  const [orgType, setOrgType] = useState<OrganizationType>("employer");
  const [userEmail, setUserEmail] = useState("");
  const [userPassword, setUserPassword] = useState("password123");
  const [userOrgId, setUserOrgId] = useState("");
  const [userRole, setUserRole] = useState("employer_admin");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteOrgName, setInviteOrgName] = useState("");
  const [inviteProfileName, setInviteProfileName] = useState("");
  const [inviteMessage, setInviteMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    const data = await listOrganizations();
    setOrgs(data);
    if (!userOrgId && data[0]) setUserOrgId(data[0].id);
  }

  async function refreshInvites() {
    setInvites(await listInvites());
  }

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [orgData, inviteData] = await Promise.all([listOrganizations(), listInvites()]);
        if (cancelled) return;
        setOrgs(orgData);
        setInvites(inviteData);
        if (orgData[0]) setUserOrgId(orgData[0].id);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError ? err.message : "Failed to load platform data");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function onCreateInvite(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setInviteMessage(null);
    try {
      await createInvite({
        email: inviteEmail,
        organization_name: inviteOrgName,
        profile_name: inviteProfileName,
      });
      setInviteEmail("");
      setInviteOrgName("");
      setInviteProfileName("");
      setInviteMessage("Invite sent.");
      await refreshInvites();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create invite failed");
    }
  }

  async function onRevokeInvite(id: string) {
    setError(null);
    try {
      await revokeInvite(id);
      await refreshInvites();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Revoke failed");
    }
  }

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

      <section className="panel" style={{ marginBottom: 18 }}>
        <h2 style={{ marginTop: 0, fontFamily: "var(--font-display)" }}>Provider invites</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Healthcare providers onboard by invite only. Sending one emails a one-time link
          that lets the invitee set a password and create their org.
        </p>
        {invites.length === 0 ? (
          <p className="muted">No invites yet.</p>
        ) : (
          <table className="rank-table" style={{ marginBottom: 18 }}>
            <thead>
              <tr>
                <th>Email</th>
                <th>Organization</th>
                <th>Status</th>
                <th>Expires</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {invites.map((invite) => (
                <tr key={invite.id}>
                  <td>{invite.email}</td>
                  <td>{invite.organization_name}</td>
                  <td>
                    <span className="chip">{invite.status}</span>
                  </td>
                  <td className="muted">{new Date(invite.expires_at).toLocaleDateString()}</td>
                  <td>
                    {invite.status === "pending" && (
                      <button
                        type="button"
                        className="btn-secondary btn"
                        style={{ padding: "6px 12px" }}
                        onClick={() => onRevokeInvite(invite.id)}
                      >
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <form onSubmit={onCreateInvite}>
          {inviteMessage && <div className="success-banner">{inviteMessage}</div>}
          <div className="form-grid">
            <div className="field">
              <label htmlFor="inviteEmail">Invitee email</label>
              <input
                id="inviteEmail"
                type="email"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="inviteOrgName">Organization name</label>
              <input
                id="inviteOrgName"
                value={inviteOrgName}
                onChange={(e) => setInviteOrgName(e.target.value)}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="inviteProfileName">Profile name</label>
              <input
                id="inviteProfileName"
                value={inviteProfileName}
                onChange={(e) => setInviteProfileName(e.target.value)}
                required
              />
            </div>
          </div>
          <button className="btn" type="submit">
            Send invite
          </button>
        </form>
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
