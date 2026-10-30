import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Item, Tool } from "../api";
import type { Names } from "../lib/flowcheck";
import { BindingForm } from "./FlowData";

const tool: Tool = {
  name: "get_fee", position: 0, revision: 1,
  body: { params: { amount: "number", account: { type: "digits", length: 4 }, note: { type: "text", required: false } }, returns: { fee: "number", currency: "text" } },
};
const first: Tool = { name: "get_balance", position: 1, revision: 1, body: { params: { n: "digits" }, returns: { balance: "number", name: "text" } } };
const d = {
  start: "gate", order: ["gate", "first", "ask", "lookup"], header: {},
  nodes: {
    gate: { type: "branch", cases: [{ when: "x", next: "first" }], else: "first" },
    first: { type: "call", tool: "get_balance", bind: { n: { const: "1234" } }, on_ok: "ask" },
    ask: { type: "ask", slot: "amount", prompt: "?", extractor: "number", next: "lookup" },
    lookup: { type: "call", tool: "get_fee", args: { amount: "{amount}" }, bind: { account: { call: "first", field: "name" } } },
  },
};
const names: Names = { source: (_r, f) => String(f), step: (id) => id };
const item = (o: Partial<Item>): Item => ({ severity: "error", source: "engine", code: "unbound", file: "f", lang: "ko", flow_id: "x", node_id: "lookup", field: null, message: "m", ...o });
afterEach(cleanup);

describe("binding a typed API", () => {
  it("shows the engine's call check under its parameter, with the path as buttons that select the step", () => {
    const onSelect = vi.fn();
    const checks = [item({ code: "not_collected", parameter: "amount", field: "amount", path: ["gate", "lookup"] })];
    render(<MemoryRouter><BindingForm d={d} id="lookup" tool={tool} tools={[tool, first]} doc={null} lang="ko" onNode={() => {}} checks={checks} names={names} onSelect={onSelect} /></MemoryRouter>);
    expect(screen.getByRole("alert").textContent).toMatch("amount: 연결한 속성(amount)을 받지 않고 이 단계에 오는 길이 있어요");
    fireEvent.click(screen.getByRole("button", { name: "gate" }));
    expect(onSelect).toHaveBeenCalledWith("gate");
  });

  it("does not count an optional parameter as open, and says so", () => {
    render(<MemoryRouter><BindingForm d={d} id="lookup" tool={tool} tools={[tool, first]} doc={null} lang="ko" onNode={() => {}} /></MemoryRouter>);
    expect(screen.getByText("선택, 연결 안 함")).toBeTruthy();
    expect(screen.queryByText(/연결 안 된 속성/)).toBeNull();   // amount is bound by args, account by a call, note is optional
  });

  it("says when the chosen response item does not fit the parameter", () => {
    render(<MemoryRouter><BindingForm d={d} id="lookup" tool={tool} tools={[tool, first]} doc={null} lang="ko" onNode={() => {}} /></MemoryRouter>);
    expect(screen.getByText(/형식이 맞지 않아요 \(받는 쪽 숫자 자리\(키패드 포함\) 4자리, 고른 항목 말 그대로\)/)).toBeTruthy();
  });
});
