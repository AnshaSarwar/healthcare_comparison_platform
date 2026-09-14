"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { ApiError, requestPasswordReset } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await requestPasswordReset(email);
      setSent(true);
    } catch (err) {
      // requestPasswordReset always returns 202 server-side, so this is a
      // network/validation error, not "email not found" (we never reveal that).
      setError(err instanceof ApiError ? err.message : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <form className="panel login-card" onSubmit={onSubmit}>
        <h1>Forgot password</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          We&apos;ll email you a link to reset your password.
        </p>
        {error && <div className="error-banner">{error}</div>}
        {sent ? (
          <div className="success-banner">
            If that email is registered, a reset link is on its way.
          </div>
        ) : (
          <>
            <div className="field">
              <label htmlFor="email">Email</label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            <button className="btn" type="submit" disabled={loading}>
              {loading ? "Sending…" : "Send reset link"}
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
