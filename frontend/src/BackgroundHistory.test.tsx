import "@testing-library/jest-dom/vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import BackgroundHistory from "./BackgroundHistory";
import { pollDelayMs } from "./api";


const history = {
  employeeId: "E0001",
  checks: [{
    checkId: "CHK-1", status: "pending", createdAt: "2026-08-25T09:00:00Z",
    completedAt: null, requestedByName: "김관리", requestedFirstName: "민준", requestedLastName: "박",
  }],
};

const detail = (status: "pending" | "clear" | "flagged") => ({
  checkId: "CHK-1", employeeId: "E0001", status,
  criminalRecord: status === "pending" ? null : status === "flagged",
  educationVerified: status === "pending" ? null : true,
  employmentVerified: status === "pending" ? null : true,
  creditScore: status === "pending" ? null : "good",
  createdAt: "2026-08-25T09:00:00Z",
  completedAt: status === "pending" ? null : "2026-08-25T09:02:00Z",
});

const jsonResponse = (body: unknown, status = 200, headers?: HeadersInit) =>
  new Response(JSON.stringify(body), { status, headers });

async function flush() {
  await act(async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

test("polling 간격은 증가하고 Retry-After가 우선한다", () => {
  expect([pollDelayMs(0), pollDelayMs(1), pollDelayMs(2), pollDelayMs(9)]).toEqual([10_000, 20_000, 30_000, 30_000]);
  expect(pollDelayMs(0, 45)).toBe(45_000);
});

test.each(["clear", "flagged"] as const)("여러 pending 후 %s가 되면 polling을 종료한다", async (finalStatus) => {
  vi.useFakeTimers();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse(history))
    .mockResolvedValueOnce(jsonResponse(detail("pending")))
    .mockResolvedValueOnce(jsonResponse(detail("pending")))
    .mockResolvedValueOnce(jsonResponse(detail(finalStatus)));
  render(<BackgroundHistory employeeId="id" onUnauthorized={vi.fn()} />);
  await flush();
  expect(screen.getByText("처리 중 · 다음 상태를 자동 확인합니다.")).toBeInTheDocument();

  await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
  await act(async () => { await vi.advanceTimersByTimeAsync(20_000); });
  expect(screen.getAllByText(finalStatus).length).toBeGreaterThan(0);
  const callsAtCompletion = fetchMock.mock.calls.length;
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetchMock).toHaveBeenCalledTimes(callsAtCompletion);
});

test("503 Retry-After 이후에 polling을 재개한다", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse(history))
    .mockResolvedValueOnce(jsonResponse({ detail: "unavailable" }, 503, { "Retry-After": "45" }))
    .mockResolvedValueOnce(jsonResponse(detail("clear")));
  render(<BackgroundHistory employeeId="id" onUnauthorized={vi.fn()} />);
  await flush();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(44_000); });
  expect(fetchMock).toHaveBeenCalledTimes(2);
  await act(async () => { await vi.advanceTimersByTimeAsync(1_000); });
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(screen.getAllByText("clear").length).toBeGreaterThan(0);
});

test("화면을 벗어나면 예약된 polling을 중단한다", async () => {
  vi.useFakeTimers();
  const fetchMock = vi.spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(jsonResponse(history))
    .mockResolvedValueOnce(jsonResponse(detail("pending")));
  const rendered = render(<BackgroundHistory employeeId="id" onUnauthorized={vi.fn()} />);
  await flush();
  expect(fetchMock).toHaveBeenCalledTimes(2);
  rendered.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(60_000); });
  expect(fetchMock).toHaveBeenCalledTimes(2);
});
