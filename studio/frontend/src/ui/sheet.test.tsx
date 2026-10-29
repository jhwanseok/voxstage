// Regression: the sheet's focus trap re-ran on every render (its owner passes a new onClose each time), so typing in
// any field threw the focus back to the first one.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sheet } from ".";

function Owner({ onClose }: { onClose: () => void }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  return (
    <Sheet open title="편집" onClose={() => onClose()}>
      <input aria-label="첫째" data-autofocus value={a} onChange={(e) => setA(e.target.value)} />
      <input aria-label="둘째" value={b} onChange={(e) => setB(e.target.value)} />
    </Sheet>
  );
}

afterEach(cleanup);

describe("Sheet focus", () => {
  it("focuses the autofocus field once and leaves the focus where the user types", () => {
    const onClose = vi.fn();
    render(<Owner onClose={onClose} />);
    expect(document.activeElement).toBe(screen.getByLabelText("첫째"));
    const second = screen.getByLabelText("둘째");
    act(() => second.focus());
    fireEvent.change(second, { target: { value: "가" } });
    fireEvent.change(second, { target: { value: "가나" } });
    expect(document.activeElement).toBe(second);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
