import { useCallback, useEffect, useRef, useState } from "react";

import type { Api } from "../api/client";
import { decrypt, deriveKey, forgetKey, rememberKey, rememberedKey, saltOf } from "./crypto";
import { PageImages } from "./images";
import { PageMenu } from "./PageMenu";
import { PasswordScreen } from "./PasswordScreen";
import { PhoneScreens } from "./PhoneScreens";
import { readSnapshot, type PageFiles, type PhoneSnapshot } from "./snapshot";
import { createSnapshotApi } from "./snapshotApi";

type Open = { step: "open"; blob: ArrayBuffer; key: CryptoKey; snapshot: PhoneSnapshot; images: PageImages; api: Api };
type State = { step: "loading" } | { step: "failed" } | { step: "locked"; blob: ArrayBuffer; wrong: boolean; busy: boolean } | Open;

const FAILED: State = { step: "failed" };

function locked(blob: ArrayBuffer, wrong = false): State {
  return { step: "locked", blob, wrong, busy: false };
}

/** Null when the key does not open the file: a wrong password or a changed salt. */
async function opened(blob: ArrayBuffer, key: CryptoKey): Promise<PhoneSnapshot | null> {
  let plain: ArrayBuffer;
  try {
    plain = await decrypt(blob, key);
  } catch {
    return null;
  }
  return readSnapshot(plain);
}

/** The snapshot with every image decrypted, ready to show whole. */
async function show(files: PageFiles, blob: ArrayBuffer, key: CryptoKey, snapshot: PhoneSnapshot, now: () => Date): Promise<Open> {
  const images = await PageImages.open(files, key, snapshot.images);
  return { step: "open", blob, key, snapshot, images, api: createSnapshotApi(snapshot, images, now) };
}

/** Opens the file with the key remembered for its salt, or asks for the password. */
async function reopen(files: PageFiles, blob: ArrayBuffer, now: () => Date): Promise<State> {
  const key = await rememberedKey(saltOf(blob));
  if (!key) return locked(blob);
  const snapshot = await opened(blob, key);
  if (!snapshot) {
    forgetKey();
    return locked(blob);
  }
  return show(files, blob, key, snapshot, now);
}

const realNow = () => new Date();

/** Asks for the password once, then shows the app's Want to go screen over the decrypted plans; the derived key stays on the phone until Lock. */
export function PhoneApp({ files, now: clock = realNow }: { files: PageFiles; now?: () => Date }) {
  const [state, setState] = useState<State>({ step: "loading" });
  const latestClock = useRef(clock);
  useEffect(() => {
    latestClock.current = clock;
  });
  const now = useCallback(() => latestClock.current(), []);

  useEffect(() => {
    let current = true;
    const load = async (): Promise<State> => {
      const blob = await files.snapshot().catch(() => null);
      return blob ? reopen(files, blob, now).catch(() => FAILED) : FAILED;
    };
    void load().then((next) => current && setState(next));
    return () => {
      current = false;
    };
  }, [files, now]);

  const images = state.step === "open" ? state.images : null;
  useEffect(() => () => images?.release(), [images]);

  useEffect(() => {
    if (state.step !== "open") return;
    const shown = state;
    const refresh = async () => {
      if (document.visibilityState !== "visible") return;
      const blob = await files.snapshot().catch(() => null);
      if (!blob) return;
      let next: State;
      try {
        const snapshot = await opened(blob, shown.key);
        next = snapshot ? await show(files, blob, shown.key, snapshot, now) : await reopen(files, blob, now);
      } catch {
        next = FAILED;
      }
      setState((previous) => {
        if (previous === shown) return next;
        if (next.step === "open") next.images.release();
        return previous;
      });
    };
    const onVisibility = () => void refresh();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [state, files, now]);

  const unlock = useCallback(
    async (blob: ArrayBuffer, password: string) => {
      setState({ step: "locked", blob, wrong: false, busy: true });
      const salt = saltOf(blob);
      try {
        const key = await deriveKey(password, salt);
        const snapshot = await opened(blob, key);
        if (!snapshot) {
          setState(locked(blob, true));
          return;
        }
        await rememberKey(key, salt);
        setState(await show(files, blob, key, snapshot, now));
      } catch {
        setState(FAILED);
      }
    },
    [files, now],
  );

  const lock = useCallback((blob: ArrayBuffer) => {
    forgetKey();
    setState(locked(blob));
  }, []);

  switch (state.step) {
    case "loading":
      return <main className="phone-message" aria-busy="true" />;
    case "failed":
      return (
        <main className="phone-message">
          <div className="empty">
            <p className="empty__title">Couldn’t load the plans</p>
            <p className="empty__text">Check the connection and reload the page.</p>
          </div>
        </main>
      );
    case "locked":
      return <PasswordScreen wrong={state.wrong} busy={state.busy} onOpen={(password) => void unlock(state.blob, password)} />;
    case "open":
      return <PhoneScreens api={state.api} tools={<PageMenu snapshot={state.snapshot} now={now()} onLock={() => lock(state.blob)} />} />;
  }
}
