import { useCallback, useEffect, useState } from "react";

import { decrypt, deriveKey, forgetKey, rememberKey, rememberedKey, saltOf } from "./crypto";
import { PasswordScreen } from "./PasswordScreen";
import { PlanList } from "./PlanList";
import { Posters, PostersContext } from "./posters";
import { readSnapshot, type PageFiles, type PhoneSnapshot } from "./snapshot";

type State =
  | { step: "loading" }
  | { step: "failed" }
  | { step: "locked"; blob: ArrayBuffer; wrong: boolean; busy: boolean }
  | { step: "open"; blob: ArrayBuffer; snapshot: PhoneSnapshot; posters: Posters };

async function open(files: PageFiles, blob: ArrayBuffer, key: CryptoKey): Promise<State> {
  const snapshot = readSnapshot(await decrypt(blob, key));
  return { step: "open", blob, snapshot, posters: new Posters(files, key) };
}

/** Asks for the password once, then shows the decrypted plans; the derived key stays on the phone until Lock. */
export function PhoneApp({ files, now = () => new Date() }: { files: PageFiles; now?: () => Date }) {
  const [state, setState] = useState<State>({ step: "loading" });

  useEffect(() => {
    let current = true;
    const load = async (): Promise<State> => {
      const blob = await files.snapshot().catch(() => null);
      if (!blob) return { step: "failed" };
      const key = await rememberedKey(saltOf(blob));
      if (key) {
        try {
          return await open(files, blob, key);
        } catch {
          forgetKey();
        }
      }
      return { step: "locked", blob, wrong: false, busy: false };
    };
    void load().then((next) => current && setState(next));
    return () => {
      current = false;
    };
  }, [files]);

  useEffect(() => () => (state.step === "open" ? state.posters.release() : undefined), [state]);

  const unlock = useCallback(
    async (blob: ArrayBuffer, password: string) => {
      setState({ step: "locked", blob, wrong: false, busy: true });
      const salt = saltOf(blob);
      const key = await deriveKey(password, salt);
      try {
        const opened = await open(files, blob, key);
        await rememberKey(key, salt);
        setState(opened);
      } catch {
        setState({ step: "locked", blob, wrong: true, busy: false });
      }
    },
    [files],
  );

  const lock = useCallback((blob: ArrayBuffer) => {
    forgetKey();
    setState({ step: "locked", blob, wrong: false, busy: false });
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
