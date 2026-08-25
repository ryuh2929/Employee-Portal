import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const employee = { id: "id", employee_number: "E0001", full_name: "박민준", date_of_birth: "1992-07-08", email: "minjun@example.com", phone: "010-1111-2222", address: "서울특별시", role: "EMPLOYEE", status: "ACTIVE" };

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
