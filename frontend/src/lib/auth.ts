const TOKEN_KEY = "benefits_token";
const ME_KEY = "benefits_me";

export type StoredMe = {
  id: string;
  email: string;
  role: "platform_admin" | "employer_admin" | "healthcare_org_admin";
  organization_id: string;
  organization_name: string;
  org_type: "employer" | "healthcare_provider";
};

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(ME_KEY);
}

export function isAuthenticated(): boolean {
  return Boolean(getToken());
}

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

export function homeForRole(role: StoredMe["role"] | undefined): string {
  if (role === "healthcare_org_admin") return "/provider";
  if (role === "platform_admin") return "/platform";
  return "/plans";
}
