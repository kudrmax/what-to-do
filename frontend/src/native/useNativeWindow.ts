import { useEffect, useState, type MouseEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { SECTIONS } from "../app/routes";
import { useThemeChoice } from "../app/theme";
import { onNativeOpenSettings, windowTheme, windowTitlebar } from "./nativeHost";
import { titlebarAction, titlebarHeight } from "./titlebarPress";

/**
 * Ties the page to the macOS app's window: the window takes the page's theme, "Settings…" opens
 * the settings screen, and the returned handler lets the strip under the title bar move the window.
 * In a plain browser it does nothing.
 */
export function useNativeWindow(): (event: MouseEvent) => void {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const [titlebar] = useState(() => windowTitlebar());
  const [theme] = useThemeChoice();

  useEffect(() => windowTheme()?.follow(theme), [theme]);
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
