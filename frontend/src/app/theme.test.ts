import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it, vi } from "vitest";

import { Theme, THEME_STORAGE_KEY } from "./theme";

class FakeSystem {
  matches: boolean;
  private listener: (() => void) | null = null;

  constructor(dark: boolean) {
    this.matches = dark;
  }

  addEventListener(_: string, listener: () => void) {
    this.listener = listener;
  }

  flip(dark: boolean) {
    this.matches = dark;
    this.listener?.();
  }
}

function setUp({ stored = null as string | null, systemDark = false } = {}) {
  const storage = new Map<string, string>(stored ? [[THEME_STORAGE_KEY, stored]] : []);
  const fakeStorage = { getItem: (key: string) => storage.get(key) ?? null, setItem: (key: string, value: string) => storage.set(key, value) } as unknown as Storage;
  const system = new FakeSystem(systemDark);
  const root = document.createElement("html");
  const theme = new Theme(fakeStorage, system as unknown as MediaQueryList, root);
  return { theme, system, root, storage };
}

describe("Theme", () => {
  it("follows the system by default", () => {
    const { theme, root } = setUp({ systemDark: true });

    expect(theme.choice()).toBe("system");
    expect(root.dataset.theme).toBe("dark");
    expect(root.style.colorScheme).toBe("dark");
  });

  it("switches live when the system does", () => {
    const { theme, system, root } = setUp();
    const listener = vi.fn();
    theme.subscribe(listener);

    system.flip(true);

    expect(root.dataset.theme).toBe("dark");
    expect(listener).toHaveBeenCalled();
  });

  it("keeps a chosen look whatever the system does", () => {
    const { theme, system, root, storage } = setUp();

    theme.choose("dark");
    system.flip(false);

    expect(root.dataset.theme).toBe("dark");
    expect(storage.get(THEME_STORAGE_KEY)).toBe("dark");
  });

  it("remembers the choice for the next visit", () => {
    const { root } = setUp({ stored: "light", systemDark: true });

    expect(root.dataset.theme).toBe("light");
  });

  it("ignores a stored value it does not know", () => {
    const { theme } = setUp({ stored: "sepia" });

    expect(theme.choice()).toBe("system");
  });

  it("shares its storage key with the script that sets the look before the first paint", () => {
    const html = readFileSync(resolve(__dirname, "../../index.html"), "utf-8");

    expect(html).toContain(`localStorage.getItem("${THEME_STORAGE_KEY}")`);
  });
});
