import { describe, expect, it } from "vitest";

import { TITLEBAR_HEIGHT_PROPERTY, titlebarAction, titlebarHeight } from "./titlebarPress";

const STRIP = 52;

function press(target: Element, overrides: Partial<{ button: number; detail: number; clientY: number }> = {}) {
  return { button: 0, detail: 1, clientY: 10, target, ...overrides };
}

describe("titlebarAction", () => {
  const empty = document.createElement("div");

  it("drags the window from an empty spot under the title bar", () => {
    expect(titlebarAction(press(empty), STRIP)).toBe("drag");
  });

  it("double-clicks the title bar on a double click there", () => {
    expect(titlebarAction(press(empty, { detail: 2 }), STRIP)).toBe("doubleClick");
  });

  it("leaves presses below the title bar to the page", () => {
    expect(titlebarAction(press(empty, { clientY: STRIP }), STRIP)).toBeNull();
  });

  it("leaves controls to the page", () => {
    const link = document.createElement("a");
    const label = document.createElement("span");
    link.append(label);

    expect(titlebarAction(press(label), STRIP)).toBeNull();
    expect(titlebarAction(press(document.createElement("button")), STRIP)).toBeNull();
  });

  it("ignores buttons other than the primary one", () => {
    expect(titlebarAction(press(empty, { button: 2 }), STRIP)).toBeNull();
  });

  it("does nothing without a title bar", () => {
    expect(titlebarAction(press(empty), 0)).toBeNull();
  });
});

describe("titlebarHeight", () => {
  it("is 0 in a plain browser", () => {
    expect(titlebarHeight(document.createElement("div"))).toBe(0);
  });

  it("reads the height the macOS app set", () => {
    const root = document.createElement("div");
    root.style.setProperty(TITLEBAR_HEIGHT_PROPERTY, "26px");

    expect(titlebarHeight(root)).toBe(26);
  });
});
