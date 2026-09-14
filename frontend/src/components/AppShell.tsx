"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { logout as logoutApi, resendVerification } from "@/lib/api";
import { clearSession, getMe, homeForRole, type StoredMe } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMeState] = useState<StoredMe | null>(null);
  const [resendState, setResendState] = useState<"idle" | "sending" | "sent" | "error">("idle");

  useEffect(() => {
    setMeState(getMe());
    setResendState("idle");
  }, [pathname]);

  async function onResendVerification() {
    if (!me) return;
    setResendState("sending");
    try {
      await resendVerification(me.email);
      setResendState("sent");
    } catch {
      setResendState("error");
    }
  }

  const role = me?.role;
  const nav =
    role === "healthcare_org_admin"
      ? [
          { href: "/provider", label: "Provider" },
          { href: "/plans", label: "Plans" },
          { href: "/chat", label: "Chat" },
        ]
      : role === "platform_admin"
        ? [
            { href: "/platform", label: "Platform" },
            { href: "/plans", label: "Plans" },
            { href: "/chat", label: "Chat" },
          ]
        : [
            { href: "/plans", label: "Plans" },
            { href: "/employer", label: "Employer" },
            { href: "/chat", label: "Chat" },
          ];

  const subtitle =
    role === "healthcare_org_admin"
      ? "Provider workspace"
      : role === "platform_admin"
        ? "Platform admin"
        : "Employer workspace";

  async function logout() {
    await logoutApi();
    clearSession();
    router.replace("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">BC</span>
          <div>
            <p className="brand-name">Benefits Compare</p>
            <p className="brand-sub">{subtitle}</p>
          </div>
        </div>
        <nav className="nav">
          {nav.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={active ? "nav-link active" : "nav-link"}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        {me && (
          <p className="brand-sub" style={{ margin: "0 0 8px", opacity: 0.85 }}>
            {me.email}
          </p>
        )}
        <button type="button" className="logout-btn" onClick={logout}>
          Log out
        </button>
        <button
          type="button"
          className="logout-btn"
          style={{ marginTop: 8 }}
          onClick={() => router.push(homeForRole(role))}
        >
          Home
        </button>
      </aside>
      <main className="main">
        {me && !me.email_verified && (
          <div className="warning-banner">
            <span>Please verify your email address ({me.email}).</span>
            {resendState === "sent" ? (
              <span>Verification email sent.</span>
            ) : (
              <button
                type="button"
                className="btn-secondary btn"
                style={{ padding: "6px 12px" }}
                onClick={onResendVerification}
                disabled={resendState === "sending"}
              >
                {resendState === "sending" ? "Sending…" : "Resend email"}
              </button>
            )}
            {resendState === "error" && <span>Couldn&apos;t resend, try again shortly.</span>}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
