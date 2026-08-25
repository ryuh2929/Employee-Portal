import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const employee = { id: "id", employee_number: "E0001", full_name: "박민준", date_of_birth: "1992-07-08", email: "minjun@example.com", phone: "010-1111-2222", address: "서울특별시", role: "EMPLOYEE", status: "ACTIVE" };
const admin = { ...employee, id: "admin-id", employee_number: "A0001", full_name: "김관리", email: "admin@example.com", role: "ADMIN" };

test("인증되지 않은 사용자는 로그인 화면을 본다", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 401 }));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
});

test("로그인한 직원은 자신의 정보를 확인한다", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify(employee), { status: 200 }));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "박민준" })).toBeInTheDocument();
  expect(screen.getByText("E0001")).toBeInTheDocument();
});

test("전화번호와 주소를 수정한다", async () => {
  document.cookie = "employee_portal_csrf=test-csrf";
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(employee), { status: 200 })).mockResolvedValueOnce(new Response(JSON.stringify({ ...employee, phone: "010-9999-9999" }), { status: 200 }));
  render(<App />);
  fireEvent.change(await screen.findByLabelText("전화번호"), { target: { value: "010-9999-9999" } });
  fireEvent.click(screen.getByRole("button", { name: "저장" }));
  await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  expect(fetchMock.mock.calls[1][1]).toEqual(expect.objectContaining({ method: "PATCH", headers: expect.objectContaining({ "X-CSRF-Token": "test-csrf" }) }));
  expect(await screen.findByText("정보가 저장되었습니다.")).toBeInTheDocument();
});

test("저장 시 세션이 만료되면 로그인 화면으로 이동한다", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response(JSON.stringify(employee), { status: 200 })).mockResolvedValueOnce(new Response(null, { status: 401 }));
  render(<App />);
  await screen.findByLabelText("전화번호");
  fireEvent.click(screen.getByRole("button", { name: "저장" }));
  expect(await screen.findByRole("heading", { name: "로그인" })).toBeInTheDocument();
  expect(screen.getByText("세션이 만료되었습니다. 다시 로그인해 주세요.")).toBeInTheDocument();
});

test("관리자는 직원 목록과 신규 등록 화면을 사용한다", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(admin), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([employee]), { status: 200 }));
  render(<App />);
  expect(await screen.findByRole("heading", { name: "직원 관리" })).toBeInTheDocument();
  expect(await screen.findByText("박민준")).toBeInTheDocument();
  expect(screen.getByText("E0001")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "신규 직원 등록" }));
  expect(screen.getByLabelText("초기 비밀번호")).toBeInTheDocument();
  expect(screen.queryByLabelText("역할")).not.toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("관리자는 확인 후 직원을 퇴사 처리하고 상태를 확인한다", async () => {
  document.cookie = "employee_portal_csrf=test-csrf";
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(admin), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([employee]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(employee), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ employeeId: "E0001", checks: [] }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ ...employee, status: "TERMINATED", terminated_at: "2026-08-25T08:00:00Z", terminated_by: "admin-id" }), { status: 200 }));
  render(<App />);
  await screen.findByText("박민준");
  fireEvent.click(screen.getByRole("button", { name: "상세" }));
  await screen.findByText("요청 이력이 없습니다.");
  fireEvent.click(await screen.findByRole("button", { name: "퇴사 처리" }));
  expect(window.confirm).toHaveBeenCalled();
  expect(await screen.findByText("상태: TERMINATED")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "퇴사 처리됨" })).toBeDisabled();
  expect(fetchMock.mock.calls[4][0]).toBe("http://localhost:8000/admin/employees/id/terminate");
  expect(fetchMock.mock.calls[4][1]).toEqual(expect.objectContaining({ method: "POST", headers: { "X-CSRF-Token": "test-csrf" } }));
});

test("관리자는 이름 제안을 수정해 Background Check를 요청한다", async () => {
  document.cookie = "employee_portal_csrf=test-csrf";
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(JSON.stringify(admin), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify([employee]), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(employee), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ employeeId: "E0001", checks: [] }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ firstName: "민준", lastName: "박", dateOfBirth: "1992-07-08" }), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ checkId: "CHK-1", employeeId: "E0001", firstName: "수정이름", lastName: "수정성", dateOfBirth: "1991-01-02", status: "pending" }), { status: 201 }));
  render(<App />);
  await screen.findByText("박민준");
  fireEvent.click(screen.getByRole("button", { name: "상세" }));
  await screen.findByText("요청 이력이 없습니다.");
  fireEvent.click(await screen.findByRole("button", { name: "Background Check 요청" }));
  fireEvent.change(await screen.findByLabelText("First name"), { target: { value: "수정이름" } });
  fireEvent.change(screen.getByLabelText("Last name"), { target: { value: "수정성" } });
  fireEvent.change(screen.getByLabelText("생년월일"), { target: { value: "1991-01-02" } });
  fireEvent.click(screen.getByRole("button", { name: "외부 검사 요청" }));
  expect(await screen.findByText("최초 상태: pending")).toBeInTheDocument();
  const request = fetchMock.mock.calls[5];
  expect(request[0]).toBe("http://localhost:8000/admin/employees/id/background-checks");
  expect(JSON.parse(String(request[1]?.body))).toEqual({ firstName: "수정이름", lastName: "수정성", dateOfBirth: "1991-01-02" });
});
