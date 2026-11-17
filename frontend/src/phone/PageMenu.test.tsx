import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { PLANS } from "./fixtures";
import { PageMenu } from "./PageMenu";

afterEach(() => vi.useRealTimers());

const trigger = () => screen.getByRole("button", { name: /^Updated / });

test("turns stale while the page stays open", () => {
  vi.useFakeTimers({ now: new Date("2026-11-18T18:00:00Z") });
  render(<PageMenu snapshot={PLANS} now={() => new Date()} onLock={() => {}} />);
  expect(trigger()).not.toHaveClass("page-menu__trigger--stale");

  act(() => vi.advanceTimersByTime(60 * 60 * 1000));

  expect(trigger()).toHaveClass("page-menu__trigger--stale");
});

test("turns stale on coming back to the page", () => {
  let now = new Date("2026-11-18T18:00:00Z");
  render(<PageMenu snapshot={PLANS} now={() => now} onLock={() => {}} />);
  expect(trigger()).not.toHaveClass("page-menu__trigger--stale");

  now = new Date("2026-11-19T09:00:00Z");
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  act(() => void fireEvent(document, new Event("visibilitychange")));

  expect(trigger()).toHaveClass("page-menu__trigger--stale");
});
