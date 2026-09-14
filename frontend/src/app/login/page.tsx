"use client";

import { FormEvent, Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchMe, login as loginApi, ApiError } from "@/lib/api";
import { getMe, homeForRole, setMe } from "@/lib/auth";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("employer@acme.com");
  const [password, setPassword] = useState("password123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const cached = getMe();
    if (cached) {
      router.replace(searchParams.get("next") || homeForRole(cached.role));
    }
  }, [router, searchParams]);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await loginApi(email, password);
      const me = await fetchMe();
      setMe(me);
      router.replace(searchParams.get("next") || homeForRole(me.role));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <form className="panel login-card" onSubmit={onSubmit}>
        <p className="chip" style={{ width: "fit-content", marginBottom: 12 }}>
          Benefits Compare
        </p>
        <h1>Sign in</h1>
        <p className="muted" style={{ marginTop: 0, marginBottom: 20 }}>
          Employer, provider, or platform access.
        </p>
        {error && <div className="error-banner">{error}</div>}
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
        <div className="field">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </div>
        <button className="btn" type="submit" disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
        <p className="hint">
          Demo: employer@acme.com · admin@healthfirst.com · platform@benefits.com /
          password123
        </p>
        <p className="hint">
          New employer? <Link href="/register">Register</Link> ·{" "}
          <Link href="/forgot-password">Forgot password?</Link>
        </p>
      </form>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="center-screen">
          <p className="muted">Loading…</p>
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
