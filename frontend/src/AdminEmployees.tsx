import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import { api, csrfToken, errorMessage } from "./api";
import type { Employee } from "./api";
import BackgroundHistory from "./BackgroundHistory";

type AdminView = "list" | "detail" | "create" | "background-check";
type BackgroundProposal = { firstName: string; lastName: string; dateOfBirth: string };
type BackgroundCreated = BackgroundProposal & { checkId: string; employeeId: string; status: "pending" | "clear" | "flagged" };

export default function AdminEmployees({ onUnauthorized, onLogout }: { onUnauthorized: () => void; onLogout: () => Promise<void> }) {
  const [view, setView] = useState<AdminView>("list");
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [selected, setSelected] = useState<Employee | null>(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [proposal, setProposal] = useState<BackgroundProposal | null>(null);
  const [backgroundResult, setBackgroundResult] = useState<BackgroundCreated | null>(null);

  const guard = (response: Response) => {
    if (response.status === 401 || response.status === 403) {
      onUnauthorized();
      return false;
    }
    return true;
  };

  const loadEmployees = async (term = "") => {
    setLoading(true); setMessage("");
    try {
      const query = term.trim() ? `?search=${encodeURIComponent(term.trim())}` : "";
      const response = await api(`/admin/employees${query}`);
      if (!guard(response)) return;
      if (!response.ok) throw new Error();
      setEmployees((await response.json()) as Employee[]);
      setView("list");
    } catch { setMessage("직원 목록을 불러오지 못했습니다."); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    void api("/admin/employees").then(async (response) => {
      if (response.status === 401 || response.status === 403) { onUnauthorized(); return; }
      if (!response.ok) throw new Error();
      const items = (await response.json()) as Employee[];
      if (active) { setEmployees(items); setLoading(false); }
    }).catch(() => {
      if (active) { setMessage("직원 목록을 불러오지 못했습니다."); setLoading(false); }
    });
    return () => { active = false; };
  }, [onUnauthorized]);

  const openDetail = async (id: string) => {
    setMessage("");
    const response = await api(`/admin/employees/${id}`);
    if (!guard(response)) return;
    if (!response.ok) { setMessage("직원 정보를 불러오지 못했습니다."); return; }
    setSelected((await response.json()) as Employee); setView("detail");
  };

  const submitSearch = (event: FormEvent) => { event.preventDefault(); void loadEmployees(search); };

  const employeePayload = (form: HTMLFormElement) => {
    const data = new FormData(form);
    return {
      employee_number: String(data.get("employee_number") ?? ""), full_name: String(data.get("full_name") ?? ""),
      date_of_birth: String(data.get("date_of_birth") ?? ""), email: String(data.get("email") ?? ""),
      phone: String(data.get("phone") ?? "") || null, address: String(data.get("address") ?? "") || null,
    };
  };

  const createEmployee = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault(); setMessage("");
    const payload = { ...employeePayload(event.currentTarget), initial_password: String(new FormData(event.currentTarget).get("initial_password") ?? "") };
    const response = await api("/admin/employees", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify(payload) });
    if (!guard(response)) return;
    if (!response.ok) { setMessage(await errorMessage(response, "직원을 등록하지 못했습니다.")); return; }
    setMessage("직원이 등록되었습니다."); await loadEmployees(search);
  };

  const updateEmployee = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    setMessage("");
    const response = await api(`/admin/employees/${selected.id}`, { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() }, body: JSON.stringify(employeePayload(event.currentTarget)) });
    if (!guard(response)) return;
    if (!response.ok) { setMessage(await errorMessage(response, "직원 정보를 수정하지 못했습니다.")); return; }
    setSelected((await response.json()) as Employee); setMessage("직원 정보가 저장되었습니다.");
  };

  const terminateEmployee = async () => {
    if (!selected || selected.status === "TERMINATED") return;
    if (!window.confirm(`${selected.full_name} 직원을 퇴사 처리하시겠습니까? 이 작업은 즉시 모든 세션을 종료합니다.`)) return;
    setMessage("");
    const response = await api(`/admin/employees/${selected.id}/terminate`, {
      method: "POST", headers: { "X-CSRF-Token": csrfToken() },
    });
    if (!guard(response)) return;
    if (!response.ok) { setMessage("퇴사 처리를 완료하지 못했습니다."); return; }
    setSelected((await response.json()) as Employee);
    setMessage("퇴사 처리가 완료되었으며 모든 세션이 종료되었습니다.");
  };

  const openBackgroundCheck = async () => {
    if (!selected) return;
    setMessage(""); setBackgroundResult(null);
    const response = await api(`/admin/employees/${selected.id}/background-checks/proposal`);
    if (!guard(response)) return;
    if (!response.ok) { setMessage("이름 제안값을 불러오지 못했습니다."); return; }
    setProposal((await response.json()) as BackgroundProposal);
    setView("background-check");
  };

  const requestBackgroundCheck = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selected) return;
    setMessage(""); setBackgroundResult(null);
    const data = new FormData(event.currentTarget);
    const payload = {
      firstName: String(data.get("firstName") ?? ""),
      lastName: String(data.get("lastName") ?? ""),
      dateOfBirth: String(data.get("dateOfBirth") ?? ""),
    };
    const response = await api(`/admin/employees/${selected.id}/background-checks`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken() },
      body: JSON.stringify(payload),
    });
    if (!guard(response)) return;
    if (!response.ok) {
      if (response.status === 504) setMessage("요청 시간이 초과되었습니다. 외부에서 생성되었을 수 있으므로 자동으로 다시 요청하지 않습니다.");
      else if (response.status === 503) setMessage("외부 서비스가 일시적으로 사용할 수 없습니다. 잠시 후 직접 다시 시도해 주세요.");
      else if (response.status === 422) setMessage("입력값을 확인해 주세요.");
      else setMessage("Background Check 요청을 처리하지 못했습니다.");
      return;
    }
    const created = (await response.json()) as BackgroundCreated;
    setBackgroundResult(created);
    setMessage("Background Check 요청이 생성되었습니다.");
  };

  const fields = (employee?: Employee, creating = false) => <>
    <label>사번<input name="employee_number" defaultValue={employee?.employee_number} maxLength={30} required /></label>
    <label>이름<input name="full_name" defaultValue={employee?.full_name} maxLength={100} required /></label>
    <label>생년월일<input name="date_of_birth" type="date" defaultValue={employee?.date_of_birth} required /></label>
    <label>이메일<input name="email" type="email" defaultValue={employee?.email} maxLength={320} required /></label>
    <label>전화번호<input name="phone" defaultValue={employee?.phone ?? ""} maxLength={30} /></label>
    <label>주소<textarea name="address" defaultValue={employee?.address ?? ""} maxLength={500} rows={3} /></label>
    {creating && <label>초기 비밀번호<input name="initial_password" type="password" required /></label>}
  </>;

  return <main className="admin-main"><section className="card admin-card">
    <header className="admin-header"><div><p className="eyebrow">관리자</p><h1>직원 관리</h1></div><div className="admin-actions">{view !== "list" && <button className="button--secondary" onClick={() => { setView("list"); setMessage(""); }}>목록으로</button>}<button className="button--secondary" onClick={() => void onLogout()}>로그아웃</button></div></header>
    {message && <p role="status" className={message.includes("못했") || message.includes("사용 중") ? "message message--error" : "message"}>{message}</p>}
    {view === "list" && <><div className="admin-toolbar"><form className="search-form" onSubmit={submitSearch}><label className="sr-only" htmlFor="employee-search">이름 또는 사번 검색</label><input id="employee-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="이름 또는 사번" /><button type="submit">검색</button></form><button onClick={() => { setMessage(""); setView("create"); }}>신규 직원 등록</button></div>{loading ? <p role="status">불러오는 중…</p> : <div className="table-wrap"><table><thead><tr><th>이름</th><th>사번</th><th>이메일</th><th>역할</th><th>상태</th><th></th></tr></thead><tbody>{employees.map((item) => <tr key={item.id}><td>{item.full_name}</td><td>{item.employee_number}</td><td>{item.email}</td><td>{item.role}</td><td>{item.status}</td><td><button className="button--link" onClick={() => void openDetail(item.id)}>상세</button></td></tr>)}</tbody></table>{employees.length === 0 && <p className="empty">검색 결과가 없습니다.</p>}</div>}</>}
    {view === "create" && <form className="employee-form" onSubmit={createEmployee}>{fields(undefined, true)}<button type="submit">등록</button></form>}
    {view === "detail" && selected && <><div className="readonly-badges"><span>역할: {selected.role}</span><span className={selected.status === "TERMINATED" ? "status--terminated" : ""}>상태: {selected.status}</span>{selected.terminated_at && <span>퇴사일: {new Date(selected.terminated_at).toLocaleString("ko-KR")}</span>}</div><form key={selected.id} className="employee-form" onSubmit={updateEmployee}>{fields(selected)}<button type="submit">저장</button></form><BackgroundHistory employeeId={selected.id} onUnauthorized={onUnauthorized} /><div className="background-zone"><div><strong>Background Check</strong><p>이름 분리 제안을 확인·수정한 뒤 외부 검사를 요청합니다.</p></div><button type="button" onClick={() => void openBackgroundCheck()}>Background Check 요청</button></div><div className="danger-zone"><div><strong>퇴사 처리</strong><p>퇴사 즉시 해당 직원의 모든 로그인 세션이 종료됩니다.</p></div><button type="button" className="button--danger" disabled={selected.status === "TERMINATED"} onClick={() => void terminateEmployee()}>{selected.status === "TERMINATED" ? "퇴사 처리됨" : "퇴사 처리"}</button></div></>}
    {view === "background-check" && selected && proposal && <><h2>{selected.full_name} Background Check</h2><p className="form-help">자동 제안값입니다. 실제 요청 전에 이름과 생년월일을 반드시 확인해 주세요.</p><form className="employee-form" onSubmit={requestBackgroundCheck}><label>First name<input name="firstName" defaultValue={proposal.firstName} maxLength={100} required /></label><label>Last name<input name="lastName" defaultValue={proposal.lastName} maxLength={100} required /></label><label>생년월일<input name="dateOfBirth" type="date" defaultValue={proposal.dateOfBirth} required /></label><button type="submit">외부 검사 요청</button></form>{backgroundResult && <div className="background-result"><strong>최초 상태: {backgroundResult.status}</strong><span>Check ID: {backgroundResult.checkId}</span><span>Employee ID: {backgroundResult.employeeId}</span>{backgroundResult.status === "pending" && <p>처리 중입니다. 반복 조회는 다음 단계에서 제공됩니다.</p>}</div>}</>}
  </section></main>;
}
