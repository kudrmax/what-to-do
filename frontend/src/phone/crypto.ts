/** Every published file: "WTD1", the 16-byte salt, the 12-byte IV, then the AES-GCM ciphertext with its tag. */
const MAGIC = "WTD1";
const SALT_START = 4;
const IV_START = 20;
const CIPHERTEXT_START = 32;
const ITERATIONS = 600_000;
const STORAGE_KEY = "phone-page-key";

export function base64ToBytes(text: string): Uint8Array {
  return Uint8Array.from(atob(text), (char) => char.charCodeAt(0));
}

function bytesToBase64(bytes: Uint8Array): string {
  return btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(""));
}

export function saltOf(blob: ArrayBuffer): Uint8Array {
  return new Uint8Array(blob.slice(SALT_START, IV_START));
}

export async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const base = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveKey"]);
  return crypto.subtle.deriveKey({ name: "PBKDF2", hash: "SHA-256", salt, iterations: ITERATIONS }, base, { name: "AES-GCM", length: 256 }, true, ["decrypt"]);
}

export async function decrypt(blob: ArrayBuffer, key: CryptoKey): Promise<ArrayBuffer> {
  if (new TextDecoder().decode(blob.slice(0, SALT_START)) !== MAGIC) throw new Error("Not a phone page file");
  const iv = new Uint8Array(blob.slice(IV_START, CIPHERTEXT_START));
  return crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, blob.slice(CIPHERTEXT_START));
}

/** The derived key, never the password, is kept on the phone, together with the salt it was derived for. */
export async function rememberKey(key: CryptoKey, salt: Uint8Array): Promise<void> {
  const raw = new Uint8Array(await crypto.subtle.exportKey("raw", key));
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ salt: bytesToBase64(salt), key: bytesToBase64(raw) }));
  } catch {
    // Without storage the password is asked on every visit.
  }
}

export async function rememberedKey(salt: Uint8Array): Promise<CryptoKey | null> {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as { salt?: unknown; key?: unknown } | null;
    if (typeof stored?.salt !== "string" || typeof stored.key !== "string" || stored.salt !== bytesToBase64(salt)) return null;
    return await crypto.subtle.importKey("raw", base64ToBytes(stored.key), "AES-GCM", true, ["decrypt"]);
  } catch {
    return null;
  }
}

export function forgetKey(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing was kept.
  }
}
