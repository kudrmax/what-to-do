import type { WindowTitlebar } from "./nativeHost";

/** Set by the macOS app on the root element: how tall its title bar is over the page, in CSS pixels. */
export const TITLEBAR_HEIGHT_PROPERTY = "--shell-titlebar-h";

const CONTROL = 'a, button, input, select, textarea, label, [role="button"], [role="menu"], .popover';
const PRIMARY_BUTTON = 0;
const DOUBLE_CLICK = 2;

export interface Press {
  button: number;
  detail: number;
  clientY: number;
  target: EventTarget | null;
}

export type TitlebarAction = keyof WindowTitlebar;

/**
 * What a press does to the macOS app's window. The page runs under the title bar, so an empty spot
 * of the strip the title bar covers moves the window, and a double click there zooms it.
 */
export function titlebarAction(press: Press, titlebarHeight: number): TitlebarAction | null {
  if (press.button !== PRIMARY_BUTTON || !(press.clientY < titlebarHeight)) return null;
  if (!(press.target instanceof Element) || press.target.closest(CONTROL)) return null;
  return press.detail === DOUBLE_CLICK ? "doubleClick" : "drag";
}

/** The title bar's height the macOS app set, or 0 in a plain browser. */
export function titlebarHeight(root: HTMLElement = document.documentElement): number {
  return parseFloat(getComputedStyle(root).getPropertyValue(TITLEBAR_HEIGHT_PROPERTY)) || 0;
}
