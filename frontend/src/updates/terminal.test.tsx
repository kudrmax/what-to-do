import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { desktopOf, TERMINAL_STEPS } from "./terminal";

describe("terminal steps", () => {
  it.each([
    ["Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15", "mac"],
    ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "windows"],
    ["Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0", "linux"],
  ] as const)("knows the computer from %s", (userAgent, desktop) => {
    expect(desktopOf(userAgent)).toBe(desktop);
  });

  it("names the keys of each computer's terminal", () => {
    const { container: windows } = render(<p>{TERMINAL_STEPS.windows.paste}</p>);
    const { container: mac } = render(<p>{TERMINAL_STEPS.mac.paste}</p>);
    expect(windows).toHaveTextContent("Ctrl V");
    expect(windows).not.toHaveTextContent("⌘");
    expect(mac).toHaveTextContent("⌘ V");
  });
});
