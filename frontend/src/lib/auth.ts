const ME_KEY = "benefits_me";

export type StoredMe = {
  id: string;
  email: string;
  role: "platform_admin" | "employer_admin" | "healthcare_org_admin";
  organization_id: string;
  organization_name: string;
  org_type: "employer" | "healthcare_provider";
  email_verified: boolean;
};

export function getMe(): StoredMe | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(ME_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as StoredMe;
  } catch {
    return null;
  }
}

export function setMe(me: StoredMe): void {
  localStorage.setItem(ME_KEY, JSON.stringify(me));
}

export function clearSession(): void {
  localStorage.removeItem(ME_KEY);
}

export function homeForRole(role: StoredMe["role"] | undefined): string {
  if (role === "healthcare_org_admin") return "/provider";
  if (role === "platform_admin") return "/platform";
  return "/plans";
}
