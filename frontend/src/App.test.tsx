import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.restoreAllMocks();
});

test("백엔드 연결 성공 상태를 표시한다", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
  );

  render(<App />);

  expect(await screen.findByText("Backend: connected")).toBeInTheDocument();
});
