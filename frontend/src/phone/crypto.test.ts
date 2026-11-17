import { beforeEach, expect, test } from "vitest";

import vector from "../../../tests/fixtures/phone_page_vector.json";
import { base64ToBytes, decrypt, deriveKey, forgetKey, rememberKey, rememberedKey, saltOf } from "./crypto";

beforeEach(() => localStorage.clear());

test("decrypts the backend's vector", async () => {
  const blob = base64ToBytes(vector.blob_base64).buffer;
  const key = await deriveKey(vector.password, saltOf(blob));
  expect(new TextDecoder().decode(await decrypt(blob, key))).toBe(vector.plaintext);
});

test("a wrong password does not decrypt", async () => {
  const blob = base64ToBytes(vector.blob_base64).buffer;
  const key = await deriveKey("wrong horse", saltOf(blob));
  await expect(decrypt(blob, key)).rejects.toThrow();
});

test("a file without the header is refused", async () => {
  const blob = base64ToBytes(vector.blob_base64);
  blob[0] = 0;
  const key = await deriveKey(vector.password, saltOf(blob.buffer));
  await expect(decrypt(blob.buffer, key)).rejects.toThrow();
});

test("the remembered key opens the file only while the salt is the same", async () => {
  const blob = base64ToBytes(vector.blob_base64).buffer;
  const salt = saltOf(blob);
  await rememberKey(await deriveKey(vector.password, salt), salt);

  const key = await rememberedKey(salt);
  expect(key).not.toBeNull();
  expect(new TextDecoder().decode(await decrypt(blob, key!))).toBe(vector.plaintext);
  expect(await rememberedKey(new Uint8Array(16))).toBeNull();

  forgetKey();
  expect(await rememberedKey(salt)).toBeNull();
});

test("broken storage means no remembered key", async () => {
  localStorage.setItem("phone-page-key", "{not json");
  expect(await rememberedKey(new Uint8Array(16))).toBeNull();
});
