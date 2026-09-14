"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { acceptInvite, ApiError, fetchMe, previewInvite } from "@/lib/api";
import { homeForRole, setMe } from "@/lib/auth";
import type { ProviderInvitePreview } from "@/lib/types";

function AcceptInviteForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [invite, setInvite] = useState<ProviderInvitePreview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!token) {
      setPreviewError("Missing or invalid invite link.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await previewInvite(token);
        if (!cancelled) setInvite(data);
      } catch (err) {
        if (!cancelled) {
          setPreviewError(
            err instanceof ApiError ? err.message : "This invite is invalid or has expired",
          );
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    setSubmitError(null);
    setLoading(true);
    try {
      await acceptInvite(token, password);
      const me = await fetchMe();
      setMe(me);
      router.replace(homeForRole(me.role));
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.message : "Could not accept invite");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <form
        className="panel login-card"
        onSubmit={onSubmit}
        style={{ width: "min(480px, 100%)" }}
      >
        <p className="chip" style={{ width: "fit-content", marginBottom: 12 }}>
          Provider invite
        </p>
        <h1>Set up your account</h1>
        {previewError && (
          <>
            <div className="error-banner">{previewError}</div>
            <p className="hint">
              Ask the platform admin who invited you to send a new invite.
            </p>
          </>
        )}
        {invite && (
          <>
            <p className="muted" style={{ marginTop: 0 }}>
              Creating <strong>{invite.organization_name}</strong> as a healthcare provider,
              signed in as <strong>{invite.email}</strong>.
            </p>
            {submitError && <div className="error-banner">{submitError}</div>}
            <div className="field">
              <label htmlFor="password">Choose a password (min 8)</label>
              <input
                id="password"
                type="password"
                autoComplete="new-password"
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>
            <button className="btn" type="submit" disabled={loading}>
              {loading ? "Creating…" : "Create account"}
            </button>
          </>
        )}
        <p className="hint">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </form>
    </div>
  );
}

export default function AcceptInvitePage() {
  return (
    <Suspense
      fallback={
        <div className="center-screen">
          <p className="muted">Loading…</p>
        </div>
      }
    >
      <AcceptInviteForm />
    </Suspense>
  );
}
