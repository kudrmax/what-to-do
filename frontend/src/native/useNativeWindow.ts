import { useEffect, useState, type MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { SECTIONS } from "../app/routes";
import { onNativeOpenSettings, windowTheme, windowTitlebar, type ThemeMode } from "./nativeHost";
import { titlebarAction, titlebarHeight } from "./titlebarPress";

/** The page has only a light look, so the window's chrome stays light even when macOS is dark. */
const PAGE_THEME: ThemeMode = "light";

/**
 * Ties the page to the macOS app's window: the window takes the page's theme, «Настройки…» opens
 * the settings screen, and the returned handler lets the strip under the title bar move the window.
 * In a plain browser it does nothing.
 */
export function useNativeWindow(): (event: MouseEvent) => void {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [titlebar] = useState(() => windowTitlebar());

  useEffect(() => windowTheme()?.follow(PAGE_THEME), []);
  useEffect(
    () =>
      onNativeOpenSettings(() => {
        if (pathname !== SECTIONS.settings.path) navigate(SECTIONS.settings.path);
      }),
    [navigate, pathname],
  );

  return (event) => {
    if (!titlebar) return;
    const action = titlebarAction(event, titlebarHeight());
    if (action) titlebar[action]();
  };
}
