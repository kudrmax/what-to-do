import { useSyncExternalStore } from "react";

import type { ThemeMode } from "../native/nativeHost";

export type ThemeChoice = ThemeMode;
export type Look = "light" | "dark";

export const THEME_CHOICES: readonly ThemeChoice[] = ["system", "light", "dark"];

/** index.html reads the same key before the first paint, so keep the two in step. */
export const THEME_STORAGE_KEY = "theme";
const DARK_QUERY = "(prefers-color-scheme: dark)";

function isChoice(value: unknown): value is ThemeChoice {
  return THEME_CHOICES.includes(value as ThemeChoice);
}

/**
 * The look of the page: the person's choice, kept in the browser, and the look it resolves to.
 * `system` follows the operating system and changes live when it does.
 */
export class Theme {
  private readonly listeners = new Set<() => void>();
  private readonly storage: Storage | null;
  private readonly systemDark: MediaQueryList;
  private readonly root: HTMLElement;
  private current: ThemeChoice;

  constructor(storage: Storage | null, systemDark: MediaQueryList, root: HTMLElement) {
    this.storage = storage;
    this.systemDark = systemDark;
    this.root = root;
    this.current = this.stored();
    systemDark.addEventListener("change", () => {
      if (this.current === "system") this.changed();
    });
    this.apply();
  }

  choice(): ThemeChoice {
    return this.current;
  }

  look(): Look {
    if (this.current === "system") return this.systemDark.matches ? "dark" : "light";
    return this.current;
  }

  choose(choice: ThemeChoice) {
    if (choice === this.current) return;
    this.current = choice;
    try {
      this.storage?.setItem(THEME_STORAGE_KEY, choice);
    } catch {
      // Without storage the choice lasts until the page is reloaded.
    }
    this.changed();
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private stored(): ThemeChoice {
    try {
      const value = this.storage?.getItem(THEME_STORAGE_KEY);
      return isChoice(value) ? value : "system";
    } catch {
      return "system";
    }
  }

  private changed() {
    this.apply();
    this.listeners.forEach((listener) => listener());
  }

  /** Native controls and scrollbars follow `color-scheme`; the colours follow `data-theme` (styles/tokens.css). */
  private apply() {
    const look = this.look();
    this.root.dataset.theme = look;
    this.root.style.colorScheme = look;
  }
}

function browserStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

let shared: Theme | null = null;

/** The page's one theme, created on first use. */
export function pageTheme(): Theme {
  shared ??= new Theme(browserStorage(), window.matchMedia(DARK_QUERY), document.documentElement);
  return shared;
}

export function useThemeChoice(theme: Theme = pageTheme()): [ThemeChoice, (choice: ThemeChoice) => void] {
  const choice = useSyncExternalStore(
    (listener) => theme.subscribe(listener),
    () => theme.choice(),
  );
  return [choice, (next) => theme.choose(next)];
}
