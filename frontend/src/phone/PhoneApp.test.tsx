import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";

import type { EventCard } from "../api/client";
import { deriveKey, rememberKey, rememberedKey } from "./crypto";
import { PhoneApp } from "./PhoneApp";
import type { PageFiles, PhoneSnapshot } from "./snapshot";

const PASSWORD = "correct horse";
const NOW = new Date("2026-11-17T18:40:00Z");

beforeEach(() => localStorage.clear());

function event(id: number, title: string, plan: "sure" | "maybe", extra: Partial<EventCard> = {}): EventCard {
  return {
    id,
    title,
    original_title: title,
    description: `About ${title}`,
    kind: "single",
    start_date: "2026-11-17",
    end_date: null,
    start_time: "19:00:00",
    rrule: null,
    venue: "Dorćol Platz",
    address: "Dobračina 59",
    price: 800,
    currency: "RSD",
    tags: ["music"],
    is_priority: false,
    booking: null,
    is_cancelled: false,
    conflicts: [],
    source_ids: [1],
    interest: null,
    plan,
    is_going: true,
    image_url: null,
    place: "Dorćol Platz",
    map_url: "https://maps.example/dorcol",
    ...extra,
  } as EventCard;
}

function snapshot(occurrences: PhoneSnapshot["occurrences"], madeAt = NOW.toISOString()): PhoneSnapshot {
  return { made_at: madeAt, city: "Belgrade", timezone: "Europe/Belgrade", today: "2026-11-17", tags: ["music", "theatre"], occurrences };
}

const PLANS = snapshot([
  { date: "2026-11-17", event: event(1, "Jazz at Dorćol", "sure"), post_url: "https://t.me/jazz/1" },
  { date: "2026-11-18", event: event(2, "Puppet theatre", "maybe", { tags: ["theatre"] }), post_url: null },
]);

function freshSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(16));
}

function seal(content: PhoneSnapshot, salt: Uint8Array, password = PASSWORD): Promise<ArrayBuffer> {
  return sealText(JSON.stringify(content), salt, password);
}

async function sealText(text: string, salt: Uint8Array, password = PASSWORD): Promise<ArrayBuffer> {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  const key = await crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt, iterations: 600_000 }, base, { name: "AES-GCM", length: 256 }, false, ["encrypt"]);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(text)));
  const blob = new Uint8Array(32 + sealed.length);
  blob.set(new TextEncoder().encode("WTD1"), 0);
  blob.set(salt, 4);
  blob.set(iv, 20);
  blob.set(sealed, 32);
  return blob.buffer;
}

function files(blob: ArrayBuffer): PageFiles {
  return { snapshot: async () => blob, file: async () => new ArrayBuffer(0) };
}

async function openWith(password: string) {
  fireEvent.change(await screen.findByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Open" }));
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

test("only_sure_chip_filters", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("Puppet theatre")).toBeInTheDocument();
  const chip = screen.getByRole("button", { name: "Only “Going for sure”" });
  fireEvent.click(chip);
  expect(chip).toHaveAttribute("aria-pressed", "true");
  expect(screen.getByText("Jazz at Dorćol")).toBeInTheDocument();
  expect(screen.queryByText("Puppet theatre")).not.toBeInTheDocument();
});

test("empty_snapshot_shows_no_plans_yet", async () => {
  render(<PhoneApp files={files(await seal(snapshot([]), freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByText("No plans yet")).toBeInTheDocument();
});

test("lock_forgets_key", async () => {
  const salt = freshSalt();
  await rememberKey(await deriveKey(PASSWORD, salt), salt);
  render(<PhoneApp files={files(await seal(PLANS, salt))} now={() => NOW} />);
  fireEvent.click(await screen.findByRole("button", { name: "Lock" }));
  expect(await screen.findByLabelText("Password")).toBeInTheDocument();
  expect(await rememberedKey(salt)).toBeNull();
});

test("an_old_snapshot_is_shown_as_stale", async () => {
  const old = snapshot(PLANS.occurrences, "2026-11-15T10:00:00Z");
  render(<PhoneApp files={files(await seal(old, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  const updated = await screen.findByRole("status");
  expect(updated).toHaveClass("phone-updated--stale");
  expect(within(updated).getByText("2 days ago")).toBeInTheDocument();
});

test("a_fresh_snapshot_is_not_stale", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  expect(await screen.findByRole("status")).not.toHaveClass("phone-updated--stale");
});

test("tapping_a_card_opens_its_details", async () => {
  render(<PhoneApp files={files(await seal(PLANS, freshSalt()))} now={() => NOW} />);
  await openWith(PASSWORD);
  fireEvent.click(await screen.findByRole("button", { name: "Jazz at Dorćol" }));
  const sheet = await screen.findByRole("dialog", { name: "Jazz at Dorćol" });
  expect(within(sheet).getByText("About Jazz at Dorćol")).toBeInTheDocument();
  expect(within(sheet).getByRole("link", { name: /Dorćol Platz/ })).toHaveAttribute("href", "https://maps.example/dorcol");
  expect(within(sheet).getByRole("link", { name: "Open post" })).toHaveAttribute("href", "https://t.me/jazz/1");
  fireEvent.click(within(sheet).getByRole("button", { name: "Close" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("a_missing_snapshot_says_so", async () => {
  const failing: PageFiles = { snapshot: async () => Promise.reject(new Error("404")), file: async () => new ArrayBuffer(0) };
  render(<PhoneApp files={failing} now={() => NOW} />);
  expect(await screen.findByText("Couldn’t load the plans")).toBeInTheDocument();
});

test("a_broken_snapshot_is_not_a_wrong_password", async () => {
  render(<PhoneApp files={files(await sealText("{not json", freshSalt()))} now={() => NOW} />);
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

  blob = await seal(snapshot([{ date: "2026-11-19", event: event(3, "Late film", "sure"), post_url: null }]), salt);
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
