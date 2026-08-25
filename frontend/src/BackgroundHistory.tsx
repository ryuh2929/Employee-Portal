import { useEffect, useState } from "react";

import { api, pollDelayMs } from "./api";

type Status = "pending" | "clear" | "flagged";
type HistoryItem = { checkId: string; status: Status; createdAt: string | null; completedAt: string | null; requestedByName: string | null; requestedFirstName: string | null; requestedLastName: string | null };
type Detail = { checkId: string; status: Status; criminalRecord: boolean | null; educationVerified: boolean | null; employmentVerified: boolean | null; creditScore: string | null; createdAt: string | null; completedAt: string | null };

const value = (item: boolean | string | null) => item === null ? "-" : typeof item === "boolean" ? (item ? "예" : "아니오") : item;
const retryAfter = (response: Response) => {
  const header = response.headers.get("Retry-After");
  if (header === null) return undefined;
  const seconds = Number(header);
  return Number.isFinite(seconds) && seconds >= 0 ? seconds : undefined;
};

export default function BackgroundHistory({ employeeId, onUnauthorized }: { employeeId: string; onUnauthorized: () => void }) {
  const [checks, setChecks] = useState<HistoryItem[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;
    const schedule = (checkId: string, retryAfter?: number) => {
      timer = setTimeout(() => { void loadDetail(checkId, true); }, pollDelayMs(attempt++, retryAfter));
    };
    const loadDetail = async (checkId: string, polling: boolean) => {
      try {
        const response = await api(`/admin/employees/${employeeId}/background-checks/${encodeURIComponent(checkId)}`, { signal: controller.signal });
        if (response.status === 401 || response.status === 403) { onUnauthorized(); return; }
        if (response.status === 503 && polling) {
          schedule(checkId, retryAfter(response)); return;
        }
        if (!response.ok) { if (!polling) setMessage("검사 상세를 불러오지 못했습니다."); return; }
        const result = (await response.json()) as Detail;
        setDetail(result);
        setChecks((current) => current.map((item) => item.checkId === result.checkId ? { ...item, status: result.status, completedAt: result.completedAt } : item));
        if (result.status === "pending") schedule(checkId);
      } catch {
        if (!controller.signal.aborted && !polling) setMessage("검사 상세를 불러오지 못했습니다.");
      }
    };
    const loadHistory = async () => {
      try {
        const response = await api(`/admin/employees/${employeeId}/background-checks`, { signal: controller.signal });
        if (response.status === 401 || response.status === 403) { onUnauthorized(); return; }
        if (response.status === 503) {
          timer = setTimeout(() => { void loadHistory(); }, pollDelayMs(attempt++, retryAfter(response))); return;
        }
        if (!response.ok) { setMessage("Background Check 이력을 불러오지 못했습니다."); return; }
        const result = (await response.json()) as { checks: HistoryItem[] };
        setChecks(result.checks);
        const pending = result.checks.find((item) => item.status === "pending");
        if (pending) await loadDetail(pending.checkId, true);
        else if (result.checks[0]) await loadDetail(result.checks[0].checkId, false);
      } catch {
        if (!controller.signal.aborted) setMessage("Background Check 이력을 불러오지 못했습니다.");
      }
    };
    void loadHistory();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [employeeId, onUnauthorized]);

  const openDetail = async (checkId: string) => {
    setMessage("");
    const response = await api(`/admin/employees/${employeeId}/background-checks/${encodeURIComponent(checkId)}`);
    if (response.status === 401 || response.status === 403) { onUnauthorized(); return; }
    if (!response.ok) { setMessage("검사 상세를 불러오지 못했습니다."); return; }
    setDetail((await response.json()) as Detail);
  };

  return <section className="history-section"><h2>Background Check 이력</h2>{message && <p role="status" className="message message--error">{message}</p>}{checks.length === 0 ? <p className="form-help">요청 이력이 없습니다.</p> : <div className="table-wrap"><table><thead><tr><th>상태</th><th>요청 시각</th><th>완료 시각</th><th>요청 관리자</th><th>요청 이름</th><th></th></tr></thead><tbody>{checks.map((item) => <tr key={item.checkId}><td>{item.status}</td><td>{item.createdAt ? new Date(item.createdAt).toLocaleString("ko-KR") : "-"}</td><td>{item.completedAt ? new Date(item.completedAt).toLocaleString("ko-KR") : "-"}</td><td>{item.requestedByName ?? "외부 요청"}</td><td>{item.requestedLastName || item.requestedFirstName ? `${item.requestedLastName ?? ""}${item.requestedFirstName ?? ""}` : "-"}</td><td><button className="button--link" onClick={() => void openDetail(item.checkId)}>결과</button></td></tr>)}</tbody></table></div>}{detail && <div className={`result-detail result-detail--${detail.status}`}><div><strong>상태</strong><span>{detail.status}</span></div><div><strong>범죄 기록</strong><span>{value(detail.criminalRecord)}</span></div><div><strong>학력 확인</strong><span>{value(detail.educationVerified)}</span></div><div><strong>경력 확인</strong><span>{value(detail.employmentVerified)}</span></div><div><strong>신용 등급</strong><span>{value(detail.creditScore)}</span></div><div><strong>요청 시각</strong><span>{detail.createdAt ? new Date(detail.createdAt).toLocaleString("ko-KR") : "-"}</span></div><div><strong>완료 시각</strong><span>{detail.completedAt ? new Date(detail.completedAt).toLocaleString("ko-KR") : "-"}</span></div>{detail.status === "pending" && <p role="status">처리 중 · 다음 상태를 자동 확인합니다.</p>}</div>}</section>;
}
