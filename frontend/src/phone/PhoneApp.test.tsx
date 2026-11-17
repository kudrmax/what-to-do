import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { deriveKey, rememberKey, rememberedKey } from "./crypto";
import { event, PASSWORD, PLANS, seal, sealBytes, snapshot } from "./fixtures";
import { PhoneApp } from "./PhoneApp";
import type { PageFiles } from "./snapshot";

const NOW = new Date("2026-11-17T18:40:00Z");

beforeEach(() => {
  localStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.useFakeTimers({ toFake: ["Date"], now: NOW });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function freshSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(16));
}

function files(blob: ArrayBuffer, images: Record<string, ArrayBuffer> = {}): PageFiles {
  return { snapshot: async () => blob, file: async (path) => images[path] ?? Promise.reject(new Error(`${path}: 404`)) };
}

async function openWith(password: string) {
  fireEvent.change(await screen.findByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
}

async function openMenu() {
  fireEvent.click(await screen.findByRole("button", { name: /^Updated / }));
}

test("wrong_password_shows_error", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith("wrong horse");
  expect(await screen.findByText("Wrong password")).toBeInTheDocument();
  expect(screen.getByLabelText("Password")).toBeInTheDocument();
  expect(screen.queryByText("Jazz at Dorćol")).not.toBeInTheDocument();
});

test("right_password_opens_the_list_and_is_remembered", async () => {
  const salt = freshSalt();
  render(<PhoneApp files={files(await seal(PLANS, salt))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("Jazz at Dorćol")).toBeInTheDocument();
  expect(await rememberedKey(salt)).not.toBeNull();
});

test("remembered_key_opens_the_list_straight_away", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  render(<PhoneApp files={files(await seal(PLANS, salt))} now={() => NOW} />);
  expect(await screen.findByText("Jazz at Dorćol")).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});

test("asks_again_when_salt_changed", async () => {
  const old = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, old), old);
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(screen.queryByText("Jazz at Dorćol")).not.toBeInTheDocument();
});

test("is_the_apps_want_to_go_screen_without_a_title_or_the_past", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  const card = await screen.findByRole("link", { name: "Jazz at Dorćol" });
  expect(within(card).getByText("About Jazz at Dorćol")).toBeInTheDocument();
  expect(within(card).getByRole("group", { name: "Interest" })).toBeInTheDocument();
  expect(within(card).getByRole("button", { name: "Interesting" })).toHaveAttribute("aria-pressed", "true");
  expect(within(card).getByRole("button", { name: "Going for sure" })).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByRole("searchbox", { name: "Search events" })).toBeInTheDocument();
  for (const chip of ["Only “Going for sure”", "Tags", "Sources", "Only with time", "Hide multi-day"]) {
    expect(screen.getByRole("button", { name: chip })).toBeInTheDocument();
  }
  expect(screen.getByRole("region", { name: "Today" })).toBeInTheDocument();
  expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Past" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Note to developer" })).not.toBeInTheDocument();
});

test("marks_do_nothing", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  const card = await screen.findByRole("link", { name: "Jazz at Dorćol" });
  fireEvent.click(within(card).getByRole("button", { name: "Maybe going" }));
  expect(within(card).getByRole("button", { name: "Going for sure" })).toHaveAttribute("aria-pressed", "true");
  expect(within(card).getByRole("button", { name: "Maybe going" })).toHaveAttribute("aria-pressed", "false");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("only_sure_chip_filters", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("Puppet theatre")).toBeInTheDocument();
  const chip = screen.getByRole("button", { name: "Only “Going for sure”" });
  fireEvent.click(chip);
  expect(await screen.findByRole("button", { name: "Only “Going for sure”", pressed: true })).toBeInTheDocument();
  await vi.waitFor(() => expect(screen.queryByText("Puppet theatre")).not.toBeInTheDocument());
  expect(screen.getByText("Jazz at Dorćol")).toBeInTheDocument();
});

test("empty_snapshot_shows_no_plans_yet", async () => {
  render(<PhoneApp files={files(await seal(snapshot([]), freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("No plans yet")).toBeInTheDocument();
  expect(screen.queryByText(/Mark an event/)).not.toBeInTheDocument();
});

test("a_search_that_finds_nothing_does_not_lead_to_the_feed", async () => {
  window.history.replaceState(null, "", "/#/?search=nothing-like-this");
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("Nothing found")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Open / })).not.toBeInTheDocument();
});

test("lock_forgets_key", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  render(<PhoneApp files={files(await seal(PLANS, salt))} now={() => NOW} />);
  await openMenu();
  fireEvent.click(await screen.findByRole("button", { name: "Lock" }));
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(await rememberedKey(salt)).toBeNull();
});

test("the_menu_says_when_the_plans_were_published", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  const trigger = await screen.findByRole("button", { name: /^Updated today at / });
  expect(trigger).not.toHaveClass("page-menu__trigger--stale");
  fireEvent.click(trigger);
  expect(within(await screen.findByRole("status")).getByText(/^today at /)).toBeInTheDocument();
});

test("an_old_snapshot_is_shown_as_stale", async () => {
  const old = { ...PLANS, made_at: "2026-11-15T10:00:00Z" };
  render(<PhoneApp files={files(await seal(old, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  const trigger = await screen.findByRole("button", { name: "Updated 2 days ago" });
  expect(trigger).toHaveClass("page-menu__trigger--stale");
  fireEvent.click(trigger);
  const updated = await screen.findByRole("status");
  expect(updated).toHaveClass("page-menu__updated--stale");
  expect(within(updated).getByText("2 days ago")).toBeInTheDocument();
});

test("an_old_snapshot_names_days_from_the_real_today_and_hides_past_ones", async () => {
  const later = new Date("2026-11-17T23:30:00Z");
  vi.setSystemTime(later);
  const old = { ...PLANS, made_at: "2026-11-16T10:00:00Z" };
  render(<PhoneApp files={files(await seal(old, freshSalt()))} now={() => later} />);
  await openWith(PASSWORD);
  expect(await screen.findByRole("region", { name: "Today" })).toHaveTextContent("Puppet theatre");
  expect(screen.queryByText("Jazz at Dorćol")).not.toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Tomorrow" })).not.toBeInTheDocument();
});

test("tapping_a_card_opens_the_apps_event_window", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  fireEvent.click(await screen.findByRole("link", { name: "Jazz at Dorćol" }));
  const window = await screen.findByRole("dialog", { name: "Jazz at Dorćol" });
  expect(within(window).getByText("About Jazz at Dorćol")).toBeInTheDocument();
  expect(within(window).getByRole("link", { name: /Dorćol Platz/ })).toHaveAttribute("href", "https://maps.example/dorcol");
  expect(await within(window).findByRole("link", { name: "Open post" })).toHaveAttribute("href", "https://t.me/jazz/1");
  expect(within(window).getByRole("tab", { name: "Original" })).toBeInTheDocument();
  expect(within(window).getByRole("link", { name: "Add to Calendar" }).getAttribute("href")).toMatch(/^data:text\/calendar/);
  fireEvent.click(within(window).getByRole("button", { name: "Close" }));
  await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("posters_are_decrypted_before_the_list_shows_and_let_go_on_lock", async () => {
  const made: string[] = [];
  const revoked: string[] = [];
  vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: () => `blob:poster-${made.push("x")}`, revokeObjectURL: (url: string) => revoked.push(url) }));
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  const withPoster = snapshot([{ date: "2026-11-17", event: event(1, "Jazz at Dorćol", "sure", { image_url: "/images/jazz.jpg" }) }]);
  withPoster.images = { "/images/jazz.jpg": "images/jazz.bin", "/images/lost.jpg": "images/lost.bin" };
  const poster = await sealBytes(new Uint8Array([1, 2, 3]), salt);
  const { container } = render(<PhoneApp files={files(await seal(withPoster, salt), { "images/jazz.bin": poster })} now={() => NOW} />);

  await screen.findByText("Jazz at Dorćol");
  expect(container.querySelector(".card__photo img")).toHaveAttribute("src", "blob:poster-1");
  expect(made).toHaveLength(1);

  await openMenu();
  fireEvent.click(await screen.findByRole("button", { name: "Lock" }));
  await screen.findByLabelText("Password");
  expect(revoked).toEqual(["blob:poster-1"]);
});

test("a_missing_snapshot_says_so", async () => {
  const failing: PageFiles = { snapshot: async () => Promise.reject(new Error("404")), file: async () => new ArrayBuffer(0) };
  render(<PhoneApp files={failing} now={() => NOW} />);
  expect(await screen.findByText("Couldn’t load the plans")).toBeInTheDocument();
});

test("a_broken_snapshot_is_not_a_wrong_password", async () => {
  render(<PhoneApp files={files(await seal("{not json", freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("Couldn’t load the plans")).toBeInTheDocument();
  expect(screen.queryByText("Wrong password")).not.toBeInTheDocument();
});

function comeBack() {
  Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
  fireEvent(document, new Event("visibilitychange"));
}

test("coming_back_to_the_page_shows_the_new_snapshot", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  let blob = await seal(PLANS, salt);
  const changing: PageFiles = { snapshot: async () => blob, file: async () => new ArrayBuffer(0) };
  render(<PhoneApp files={changing} now={() => NOW} />);
  expect(await screen.findByText("Jazz at Dorćol")).toBeInTheDocument();

  blob = await seal(snapshot([{ date: "2026-11-19", event: event(3, "Late film", "sure") }]), salt);
  comeBack();

  expect(await screen.findByText("Late film")).toBeInTheDocument();
  expect(screen.queryByText("Jazz at Dorćol")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
});

test("coming_back_after_a_password_change_asks_again", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  let blob = await seal(PLANS, salt);
  const changing: PageFiles = { snapshot: async () => blob, file: async () => new ArrayBuffer(0) };
  render(<PhoneApp files={changing} now={() => NOW} />);
  expect(await screen.findByText("Jazz at Dorćol")).toBeInTheDocument();

  blob = await seal(PLANS, freshSalt(), "new password");
  comeBack();

  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
});

test("coming_back_offline_keeps_the_list", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  const blob = await seal(PLANS, salt);
  let online = true;
  const flaky: PageFiles = { snapshot: async () => (online ? blob : Promise.reject(new Error("offline"))), file: async () => new ArrayBuffer(0) };
  render(<PhoneApp files={flaky} now={() => NOW} />);
  expect(await screen.findByText("Jazz at Dorćol")).toBeInTheDocument();

  online = false;
  comeBack();
  await new Promise((resolve) => setTimeout(resolve, 20));

  expect(screen.getByText("Jazz at Dorćol")).toBeInTheDocument();
});
