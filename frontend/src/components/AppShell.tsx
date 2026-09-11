"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { clearToken, getMe, homeForRole, type StoredMe } from "@/lib/auth";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMeState] = useState<StoredMe | null>(null);

  useEffect(() => {
    setMeState(getMe());
  }, [pathname]);

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

  function logout() {
    clearToken();
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
      <main className="main">{children}</main>
    </div>
  );
}
