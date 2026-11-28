import { describe, expect, it, vi } from "vitest";

import { keepTooltipsInView, tipAlign } from "./tooltips";

const WINDOW = 1200;

describe("tooltip placement", () => {
  it("centres a tooltip that fits", () => {
    expect(tipAlign({ left: 500, right: 600 }, 200, WINDOW)).toBe("center");
  });

  it("lines a tooltip up with the element's right edge near the right of the window", () => {
    expect(tipAlign({ left: 1050, right: 1160 }, 320, WINDOW)).toBe("end");
  });

  it("lines a tooltip up with the element's left edge near the left of the window", () => {
    expect(tipAlign({ left: 10, right: 60 }, 200, WINDOW)).toBe("start");
  });

  it("marks the hovered element so its tooltip stays inside the window", () => {
    keepTooltipsInView(document);
    const button = document.createElement("button");
    button.dataset.tip = "Collect what’s new from every source";
    document.body.append(button);
    vi.spyOn(button, "getBoundingClientRect").mockReturnValue(new DOMRect(1050, 40, 110, 38));
    vi.spyOn(HTMLElement.prototype, "offsetWidth", "get").mockReturnValue(320);
    vi.spyOn(document.documentElement, "clientWidth", "get").mockReturnValue(WINDOW);

    button.dispatchEvent(new Event("pointerover", { bubbles: true }));

    expect(button.dataset.tipAlign).toBe("end");
  });
});
