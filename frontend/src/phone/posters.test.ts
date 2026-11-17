import { afterEach, expect, test, vi } from "vitest";

import { deriveKey } from "./crypto";
import { Posters } from "./posters";

afterEach(() => vi.unstubAllGlobals());

test("a poster that finishes after release is revoked at once", async () => {
  let created = 0;
  const revoked: string[] = [];
  vi.stubGlobal("URL", { ...URL, createObjectURL: () => `blob:${++created}`, revokeObjectURL: (url: string) => revoked.push(url) });
  const salt = new Uint8Array(16);
  const key = await deriveKey("pw", salt);
  const iv = new Uint8Array(12);
  const sealed = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await crypto.subtle.importKey("raw", await crypto.subtle.exportKey("raw", key), "AES-GCM", false, ["encrypt"]), new Uint8Array([1, 2, 3])));
  const blob = new Uint8Array(32 + sealed.length);
  blob.set(new TextEncoder().encode("WTD1"));
  blob.set(sealed, 32);
  let arrive: () => void = () => {};
  const files = { snapshot: async () => new ArrayBuffer(0), file: () => new Promise<ArrayBuffer>((resolve) => (arrive = () => resolve(blob.buffer))) };

  const posters = new Posters(files, key);
  const pending = posters.url("images/a.bin");
  posters.release();
  arrive();

  expect(await pending).toBeNull();
  expect(revoked).toEqual(["blob:1"]);
});
