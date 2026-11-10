import { describe, expect, it, vi } from "vitest";

import {
  CHECK_FOR_UPDATES_EVENT,
  OPEN_SETTINGS_EVENT,
  THEME_HANDLER,
  TITLEBAR_HANDLER,
  onNativeCheckForUpdates,
  onNativeOpenSettings,
  windowTheme,
  windowTitlebar,
} from "./nativeHost";

const hostWindow = (name: string) => {
  const postMessage = vi.fn().mockResolvedValue(null);
  return { win: { webkit: { messageHandlers: { [name]: { postMessage } } } } as unknown as Window, postMessage };
};

describe("windowTitlebar", () => {
  it("is absent in a plain browser", () => {
    expect(windowTitlebar({} as Window)).toBeNull();
  });

  it("asks the macOS app to drag and to double-click its title bar", () => {
    const { win, postMessage } = hostWindow(TITLEBAR_HANDLER);

    windowTitlebar(win)?.drag();
    windowTitlebar(win)?.doubleClick();

    expect(postMessage.mock.calls).toEqual([["drag"], ["doubleClick"]]);
  });
});

describe("windowTheme", () => {
  it("is absent in a plain browser", () => {
    expect(windowTheme({} as Window)).toBeNull();
  });

  it("tells the macOS app which theme the window follows", () => {
    const { win, postMessage } = hostWindow(THEME_HANDLER);

    windowTheme(win)?.follow("system");
    windowTheme(win)?.follow("light");

    expect(postMessage.mock.calls).toEqual([["system"], ["light"]]);
  });
});

describe.each([
  ["onNativeOpenSettings", onNativeOpenSettings, OPEN_SETTINGS_EVENT],
  ["onNativeCheckForUpdates", onNativeCheckForUpdates, CHECK_FOR_UPDATES_EVENT],
])("%s", (_, subscribe, event) => {
  it("calls back on the macOS app's menu item until unsubscribed", () => {
    const win = new EventTarget() as Window;
    const listener = vi.fn();

    const unsubscribe = subscribe(listener, win);
    win.dispatchEvent(new CustomEvent(event));
    unsubscribe();
    win.dispatchEvent(new CustomEvent(event));

    expect(listener).toHaveBeenCalledOnce();
  });
});
