import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createApi, type ChangelogEntry, type UpdateStatus } from "../api/client";
import { ApiContext } from "../api/queries";
import { UpdateIndicator, UpdatesProvider } from "./UpdatesProvider";
import { UpdatesSection } from "./UpdatesSection";

const ENTRY: ChangelogEntry = {
  version: "1.1.0",
  released_on: "2026-11-20",
  summary: "Календарь недели.",
  sections: [{ title: "Календарь", html: "<p>Неделя целиком.</p>" }],
};

function status(overrides: Partial<UpdateStatus> = {}): UpdateStatus {
  return {
    current: "1.0.0",
    latest: "1.1.0",
    available: true,
    entries: [ENTRY],
    check_failed: false,
    restart_command: "cd /app && make down && make up",
    update_command: "cd /app && make update",
    ...overrides,
  };
}

function setup(children: ReactNode, { updates = status(), unseen = [] as ChangelogEntry[] } = {}) {
  const api = createApi("");
  const spies = {
    updates: vi.spyOn(api, "updates").mockResolvedValue(updates),
    updateState: vi.spyOn(api, "updateState").mockResolvedValue({ state: "idle", log_tail: "", steps: [] }),
    startUpdate: vi.spyOn(api, "startUpdate").mockResolvedValue(undefined),
    version: vi.spyOn(api, "version").mockResolvedValue({ version: "1.0.0" }),
    unseen: vi.spyOn(api, "unseenChangelog").mockResolvedValue(unseen),
    seen: vi.spyOn(api, "markChangelogSeen").mockResolvedValue(undefined),
    changelog: vi.spyOn(api, "changelog").mockResolvedValue([ENTRY]),
  };
  const reload = vi.fn();
  render(
    <ApiContext.Provider value={api}>
      <UpdatesProvider reload={reload}>{children}</UpdatesProvider>
    </ApiContext.Provider>,
  );
  return { spies, reload };
}

afterEach(() => vi.useRealTimers());

/** Lets the click's promise settle, then two seconds pass: one poll of the running update. */
async function onePoll() {
  await act(async () => {
    await Promise.resolve();
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2_000);
  });
}

describe("updates", () => {
  it("shows the pill only while a newer release is out", async () => {
    setup(<UpdateIndicator />, { updates: status({ available: false, latest: "1.0.0", entries: [] }) });
    await waitFor(() => expect(screen.queryByText("Новая версия")).toBeNull());
  });

  it("opens what the update brings and starts it", async () => {
    const { spies } = setup(<UpdateIndicator />);
    fireEvent.click(await screen.findByText("Новая версия"));
    expect(screen.getByRole("dialog", { name: "Вышла новая версия" })).toBeTruthy();
    expect(screen.getByText("Неделя целиком.")).toBeTruthy();
    spies.updateState.mockResolvedValue({ state: "running", log_tail: "", steps: [{ title: "Скачиваем v1.1.0", status: "current" }] });
    vi.useFakeTimers();
    fireEvent.click(screen.getByText("Обновить до 1.1.0"));
    await act(async () => {
      await Promise.resolve();
    });
    expect(spies.startUpdate).toHaveBeenCalled();
    expect(screen.getByRole("alertdialog", { name: "Приложение обновляется" })).toBeTruthy();
    expect(screen.getByText("cd /app && make down && make up")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000);
    });
    expect(screen.getByText("Скачиваем v1.1.0")).toBeTruthy();
  });

  it("reloads the page once the server comes back on the new version", async () => {
    const { spies, reload } = setup(<UpdateIndicator />);
    fireEvent.click(await screen.findByText("Новая версия"));
    vi.useFakeTimers();
    fireEvent.click(screen.getByText("Обновить до 1.1.0"));
    spies.updateState.mockRejectedValue(new Error("down"));
    spies.version.mockResolvedValue({ version: "1.1.0" });
    await onePoll();
    expect(reload).toHaveBeenCalled();
  });

  it("explains a failed update and how to run it by hand", async () => {
    const { spies } = setup(<UpdateIndicator />);
    spies.updateState.mockResolvedValue({ state: "failed", log_tail: "npm ERR", steps: [] });
    fireEvent.click(await screen.findByText("Новая версия"));
    vi.useFakeTimers();
    fireEvent.click(screen.getByText("Обновить до 1.1.0"));
    await onePoll();
    expect(screen.getByRole("alertdialog", { name: "Обновление не удалось" })).toBeTruthy();
    expect(screen.getByText("npm ERR")).toBeTruthy();
    expect(screen.getByText("cd /app && make update")).toBeTruthy();
  });

  it("shows what's new once and remembers it was seen", async () => {
    const { spies } = setup(null, { unseen: [ENTRY] });
    expect(await screen.findByRole("dialog", { name: "Что нового" })).toBeTruthy();
    fireEvent.click(screen.getByLabelText("Закрыть"));
    expect(spies.seen).toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "Что нового" })).toBeNull();
  });

  it("settings tell the version, check now and open the history", async () => {
    const { spies } = setup(<UpdatesSection />, { updates: status({ available: false, latest: "1.0.0", entries: [] }) });
    expect(await screen.findByText("Версия 1.0.0")).toBeTruthy();
    fireEvent.click(screen.getByText("Проверить обновления"));
    expect(await screen.findByText("У вас последняя версия, 1.0.0")).toBeTruthy();
    expect(spies.updates).toHaveBeenLastCalledWith(true);
    fireEvent.click(screen.getByText("История изменений"));
    expect(await screen.findByRole("dialog", { name: "История изменений" })).toBeTruthy();
  });
});
