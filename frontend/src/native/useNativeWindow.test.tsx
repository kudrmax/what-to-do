import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SECTIONS } from "../app/routes";
import { OPEN_SETTINGS_EVENT, THEME_HANDLER, TITLEBAR_HANDLER } from "./nativeHost";
import { TITLEBAR_HEIGHT_PROPERTY } from "./titlebarPress";
import { useNativeWindow } from "./useNativeWindow";

function Shell() {
  const onMouseDown = useNativeWindow();
  return (
    <div data-testid="shell" onMouseDown={onMouseDown}>
      <p>{useLocation().pathname}</p>
    </div>
  );
}

const renderShell = () =>
  render(
    <MemoryRouter initialEntries={[SECTIONS.feed.path]}>
      <Shell />
    </MemoryRouter>,
  );

describe("useNativeWindow in a plain browser", () => {
  it("leaves presses to the page", () => {
    renderShell();

    expect(() => fireEvent.mouseDown(screen.getByTestId("shell"), { clientY: 1 })).not.toThrow();
  });
});

describe("useNativeWindow in the macOS app", () => {
  const titlebar = vi.fn();
  const theme = vi.fn();

  beforeEach(() => {
    Object.assign(window, {
      webkit: { messageHandlers: { [TITLEBAR_HANDLER]: { postMessage: titlebar }, [THEME_HANDLER]: { postMessage: theme } } },
    });
    document.documentElement.style.setProperty(TITLEBAR_HEIGHT_PROPERTY, "52px");
  });

  afterEach(() => {
    delete (window as { webkit?: unknown }).webkit;
    document.documentElement.style.removeProperty(TITLEBAR_HEIGHT_PROPERTY);
    vi.clearAllMocks();
  });

  it("keeps the window light, as the page is", () => {
    renderShell();

    expect(theme).toHaveBeenCalledWith("light");
  });

  it("opens the settings screen from the app menu", () => {
    renderShell();

    fireEvent(window, new CustomEvent(OPEN_SETTINGS_EVENT));

    expect(screen.getByText(SECTIONS.settings.path)).toBeInTheDocument();
  });

  it("moves the window from the strip under the title bar", () => {
    renderShell();

    fireEvent.mouseDown(screen.getByTestId("shell"), { clientY: 20, detail: 1 });
    fireEvent.mouseDown(screen.getByTestId("shell"), { clientY: 200, detail: 1 });

    expect(titlebar.mock.calls).toEqual([["drag"]]);
  });
});
