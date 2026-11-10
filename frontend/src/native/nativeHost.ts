// Capabilities of the macOS app (macos/) around the page. Absent in a plain browser.

export const TITLEBAR_HANDLER = "titlebar";
export const THEME_HANDLER = "theme";
export const OPEN_SETTINGS_EVENT = "nativeopensettings";
export const CHECK_FOR_UPDATES_EVENT = "nativecheckforupdates";

export type ThemeMode = "light" | "dark" | "system";

interface MessageHandler {
  postMessage(body: unknown): Promise<unknown> | void;
}

interface ShellWindow {
  webkit?: { messageHandlers?: Record<string, MessageHandler | undefined> };
}

function handler(win: Window, name: string): MessageHandler | undefined {
  return (win as ShellWindow).webkit?.messageHandlers?.[name];
}

export interface WindowTitlebar {
  /** Moves the window while the mouse is held, as dragging the title bar does. */
  drag(): void;
  /** Does what a double click on the title bar does in System Settings. */
  doubleClick(): void;
}

/** The macOS app's window, whose title bar the page covers. */
export function windowTitlebar(win: Window = window): WindowTitlebar | null {
  const titlebar = handler(win, TITLEBAR_HANDLER);
  if (!titlebar) return null;
  return {
    drag() {
      void titlebar.postMessage("drag");
    },
    doubleClick() {
      void titlebar.postMessage("doubleClick");
    },
  };
}

export interface WindowTheme {
  /** Makes the window's chrome light or dark with the page, or lets both follow macOS for `system`. */
  follow(mode: ThemeMode): void;
}

/**
 * The macOS app's window appearance. WebKit answers `prefers-color-scheme` from the window's
 * appearance, not from macOS, so the page cannot follow the system unless the window does.
 */
export function windowTheme(win: Window = window): WindowTheme | null {
  const theme = handler(win, THEME_HANDLER);
  if (!theme) return null;
  return {
    follow(mode) {
      void theme.postMessage(mode);
    },
  };
}

/** Calls back when the macOS app's «Настройки…» menu item (⌘,) is chosen; returns the unsubscribe. */
export function onNativeOpenSettings(listener: () => void, win: Window = window): () => void {
  win.addEventListener(OPEN_SETTINGS_EVENT, listener);
  return () => win.removeEventListener(OPEN_SETTINGS_EVENT, listener);
}

/** Calls back when the macOS app's «Проверить обновления…» menu item is chosen; returns the unsubscribe. */
export function onNativeCheckForUpdates(listener: () => void, win: Window = window): () => void {
  win.addEventListener(CHECK_FOR_UPDATES_EVENT, listener);
  return () => win.removeEventListener(CHECK_FOR_UPDATES_EVENT, listener);
}
