export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const CSRF_COOKIE_NAME = "employee_portal_csrf";

export type Employee = {
  id: string;
  employee_number: string;
  full_name: string;
  date_of_birth?: string;
  email: string;
  phone?: string | null;
  address?: string | null;
  role: "EMPLOYEE" | "ADMIN";
  status: "ACTIVE" | "TERMINATED";
  terminated_at?: string | null;
  terminated_by?: string | null;
};

export function csrfCookie(): string {
  const prefix = `${CSRF_COOKIE_NAME}=`;
  const cookie = document.cookie.split(";").map((value) => value.trim()).find((value) => value.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : "";
}

export async function api(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API_BASE_URL}${path}`, { ...init, credentials: "include" });
}

export async function errorMessage(response: Response, fallback: string): Promise<string> {
  if (response.status === 409) return "사번 또는 이메일이 이미 사용 중입니다.";
  try {
    const body = (await response.json()) as { detail?: string };
    return typeof body.detail === "string" ? body.detail : fallback;
  } catch {
    return fallback;
  }
}

export function pollDelayMs(attempt: number, retryAfterSeconds?: number): number {
  if (retryAfterSeconds !== undefined && retryAfterSeconds >= 0) return retryAfterSeconds * 1000;
  return [10_000, 20_000, 30_000][Math.min(attempt, 2)];
}
