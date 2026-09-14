"use client";

import { FormEvent, Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ApiError, confirmPasswordReset } from "@/lib/api";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) {
      setError("Missing or invalid reset link.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await confirmPasswordReset(token, password);
      setDone(true);
      setTimeout(() => router.replace("/login"), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <form className="panel login-card" onSubmit={onSubmit}>
        <h1>Reset password</h1>
        {!token && <div className="error-banner">Missing or invalid reset link.</div>}
        {error && <div className="error-banner">{error}</div>}
        {done ? (
          <div className="success-banner">
            Password updated. You&apos;ve been signed out everywhere — redirecting to sign in…
          </div>
        ) : (
          <>
            <div className="field">
              <label htmlFor="password">New password (min 8)</label>
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
            <button className="btn" type="submit" disabled={loading || !token}>
              {loading ? "Updating…" : "Update password"}
            </button>
          </>
        )}
        <p className="hint">
          <Link href="/login">Back to sign in</Link>
        </p>
      </form>
    </div>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="center-screen">
          <p className="muted">Loading…</p>
        </div>
      }
    >
      <ResetPasswordForm />
    </Suspense>
  );
}
