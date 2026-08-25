import { useEffect, useState } from "react";
import type { FormEvent } from "react";

import AdminEmployees from "./AdminEmployees";
import { api, csrfCookie } from "./api";
import type { Employee } from "./api";

type View = "loading" | "login" | "profile" | "admin";

function App() {
  const [view, setView] = useState<View>("loading");
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);

  const showProfile = (profile: Employee) => {
    setEmployee(profile); setPhone(profile.phone ?? ""); setAddress(profile.address ?? ""); setView(profile.role === "ADMIN" ? "admin" : "profile");
  };
  const showLogin = (notice = "") => {
    setEmployee(null); setPassword(""); setMessage(notice); setView("login");
  };

  useEffect(() => {
    void api("/employees/me").then(async (response) => {
      if (response.status === 401) { showLogin(); return; }
      if (!response.ok) throw new Error();
      showProfile((await response.json()) as Employee);
    }).catch(() => showLogin("서버에 연결할 수 없습니다."));
  }, []);

  const login = async (event: FormEvent) => {
    event.preventDefault(); setMessage("");
    try {
      const csrfResponse = await api("/auth/csrf");
      if (!csrfResponse.ok) throw new Error();
      const { csrf_token } = (await csrfResponse.json()) as { csrf_token: string };
      const response = await api("/auth/login", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf_token }, body: JSON.stringify({ email, password }) });
      if (response.status === 401) { setMessage("이메일 또는 비밀번호를 확인해 주세요."); return; }
      if (!response.ok) throw new Error();
      showProfile((await response.json()) as Employee);
    } catch { setMessage("로그인 요청을 처리하지 못했습니다."); }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault(); setSaving(true); setMessage("");
    try {
      const response = await api("/employees/me", { method: "PATCH", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfCookie() }, body: JSON.stringify({ phone: phone || null, address: address || null }) });
      if (response.status === 401) { showLogin("세션이 만료되었습니다. 다시 로그인해 주세요."); return; }
      if (!response.ok) throw new Error();
      showProfile((await response.json()) as Employee); setMessage("정보가 저장되었습니다.");
    } catch { setMessage("정보를 저장하지 못했습니다."); }
    finally { setSaving(false); }
  };

  if (view === "loading") return <main><p role="status">로그인 상태를 확인하고 있습니다.</p></main>;
  if (view === "login") return <main><section className="card login-card"><p className="eyebrow">Employee Portal</p><h1>로그인</h1><form onSubmit={login}><label>이메일<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label><label>비밀번호<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>{message && <p role="alert" className="message message--error">{message}</p>}<button type="submit">로그인</button></form></section></main>;
  if (view === "admin") return <AdminEmployees onUnauthorized={() => showLogin("관리자 세션이 만료되었거나 접근 권한이 없습니다.")} />;

  return (
    <main><section className="card profile-card"><p className="eyebrow">내 정보</p><h1>{employee?.full_name}</h1><dl className="profile-details"><div><dt>사번</dt><dd>{employee?.employee_number}</dd></div><div><dt>생년월일</dt><dd>{employee?.date_of_birth}</dd></div><div><dt>이메일</dt><dd>{employee?.email}</dd></div></dl><form onSubmit={save}><label>전화번호<input value={phone} onChange={(e) => setPhone(e.target.value)} maxLength={30} /></label><label>주소<textarea value={address} onChange={(e) => setAddress(e.target.value)} maxLength={500} rows={3} /></label>{message && <p role="status" className="message">{message}</p>}<button type="submit" disabled={saving}>{saving ? "저장 중…" : "저장"}</button></form></section></main>
  );
}

export default App;

