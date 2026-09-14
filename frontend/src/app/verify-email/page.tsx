"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ApiError, verifyEmail } from "@/lib/api";

type Status = "verifying" | "success" | "error";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<Status>("verifying");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setError("Missing verification token.");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        await verifyEmail(token);
        if (!cancelled) setStatus("success");
      } catch (err) {
        if (!cancelled) {
          setStatus("error");
          setError(err instanceof ApiError ? err.message : "Verification failed");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return (
    <div className="center-screen">
      <div className="panel login-card">
        <h1>Verify your email</h1>
        {status === "verifying" && <p className="muted">Confirming your email address…</p>}
        {status === "success" && (
          <>
            <div className="success-banner">Your email address has been verified.</div>
            <Link className="btn" href="/login">
              Sign in
            </Link>
          </>
        )}
        {status === "error" && (
          <>
            <div className="error-banner">{error}</div>
            <p className="hint">
              The link may have expired. You can request a new one from{" "}
              <Link href="/login">the sign-in page</Link> once you&apos;re logged in.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense
      fallback={
        <div className="center-screen">
          <p className="muted">Loading…</p>
        </div>
      }
    >
      <VerifyEmailContent />
    </Suspense>
  );
}
