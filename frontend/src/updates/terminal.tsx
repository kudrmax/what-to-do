import type { ReactNode } from "react";

export type Desktop = "mac" | "windows" | "linux";

/** Which computer the page is open on: the terminal and its keys differ. */
export function desktopOf(userAgent: string): Desktop {
  if (/Windows/i.test(userAgent)) return "windows";
  if (/Mac OS X|Macintosh/i.test(userAgent)) return "mac";
  return "linux";
}

interface TerminalSteps {
  open: ReactNode;
  paste: ReactNode;
}

export const TERMINAL_STEPS: Record<Desktop, TerminalSteps> = {
  mac: {
    open: (
      <>
        Open Terminal: press <kbd>⌘</kbd> <kbd>Space</kbd>, type <b>Terminal</b> and press <kbd>Return</kbd>.
      </>
    ),
    paste: (
      <>
        Click <b>Copy</b>, click in the Terminal window, then press <kbd>⌘</kbd> <kbd>V</kbd> and <kbd>Return</kbd>.
      </>
    ),
  },
  windows: {
    open: (
      <>
        Open PowerShell: press <kbd>Win</kbd>, type <b>PowerShell</b> and press <kbd>Enter</kbd>.
      </>
    ),
    paste: (
      <>
        Click <b>Copy</b>, click in the PowerShell window, then press <kbd>Ctrl</kbd> <kbd>V</kbd> and <kbd>Enter</kbd>.
      </>
    ),
  },
  linux: {
    open: (
      <>
        Open a terminal: press <kbd>Ctrl</kbd> <kbd>Alt</kbd> <kbd>T</kbd>.
      </>
    ),
    paste: (
      <>
        Click <b>Copy</b>, click in the terminal window, then press <kbd>Ctrl</kbd> <kbd>Shift</kbd> <kbd>V</kbd> and <kbd>Enter</kbd>.
      </>
    ),
  },
};
