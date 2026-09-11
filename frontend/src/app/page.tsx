"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { fetchMe } from "@/lib/api";
import { getMe, homeForRole, isAuthenticated, setMe } from "@/lib/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!isAuthenticated()) {
        router.replace("/login");
        return;
      }
      let me = getMe();
      if (!me) {
        try {
          me = await fetchMe();
          if (!cancelled) setMe(me);
        } catch {
          if (!cancelled) router.replace("/login");
          return;
        }
      }
      if (!cancelled) router.replace(homeForRole(me.role));
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  return (
    <div className="center-screen">
      <p className="muted">Loading…</p>
    </div>
  );
}
