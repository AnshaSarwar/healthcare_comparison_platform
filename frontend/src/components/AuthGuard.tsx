"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { fetchMe } from "@/lib/api";
import { getMe, getToken, isAuthenticated, setMe } from "@/lib/auth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!isAuthenticated()) {
        router.replace(`/login?next=${encodeURIComponent(pathname)}`);
        return;
      }
      if (!getMe() && getToken()) {
        try {
          const me = await fetchMe();
          if (!cancelled) setMe(me);
        } catch {
          if (!cancelled) {
            router.replace("/login");
            return;
          }
        }
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

  if (!ready) {
    return (
      <div className="center-screen">
        <p className="muted">Checking session…</p>
      </div>
    );
  }

  return <>{children}</>;
}
