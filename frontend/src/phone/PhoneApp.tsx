import { useCallback, useEffect, useState } from "react";

import { decrypt, deriveKey, forgetKey, rememberKey, rememberedKey, saltOf } from "./crypto";
import { PasswordScreen } from "./PasswordScreen";
import { PlanList } from "./PlanList";
import { Posters, PostersContext } from "./posters";
import { readSnapshot, type PageFiles, type PhoneSnapshot } from "./snapshot";

type Open = { step: "open"; blob: ArrayBuffer; key: CryptoKey; snapshot: PhoneSnapshot; posters: Posters };
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

/** Opens the file with the key remembered for its salt, or asks for the password. */
async function reopen(files: PageFiles, blob: ArrayBuffer): Promise<State> {
  const key = await rememberedKey(saltOf(blob));
  if (!key) return locked(blob);
  const snapshot = await opened(blob, key);
  if (!snapshot) {
    forgetKey();
    return locked(blob);
  }
  return { step: "open", blob, key, snapshot, posters: new Posters(files, key) };
}

/** Asks for the password once, then shows the decrypted plans; the derived key stays on the phone until Lock. */
export function PhoneApp({ files, now = () => new Date() }: { files: PageFiles; now?: () => Date }) {
  const [state, setState] = useState<State>({ step: "loading" });

  useEffect(() => {
    let current = true;
    const load = async (): Promise<State> => {
      const blob = await files.snapshot().catch(() => null);
      return blob ? reopen(files, blob).catch(() => FAILED) : FAILED;
    };
    void load().then((next) => current && setState(next));
    return () => {
      current = false;
    };
  }, [files]);

  const posters = state.step === "open" ? state.posters : null;
  useEffect(() => () => posters?.release(), [posters]);

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
        next = snapshot ? { ...shown, blob, snapshot } : await reopen(files, blob);
      } catch {
        next = FAILED;
      }
      setState((previous) => (previous === shown ? next : previous));
    };
    const onVisibility = () => void refresh();
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [state, files]);

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
        setState({ step: "open", blob, key, snapshot, posters: new Posters(files, key) });
      } catch {
        setState(FAILED);
      }
    },
    [files],
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
      return (
        <PostersContext.Provider value={state.posters}>
          <PlanList snapshot={state.snapshot} now={now()} onLock={() => lock(state.blob)} />
        </PostersContext.Provider>
      );
  }
}
