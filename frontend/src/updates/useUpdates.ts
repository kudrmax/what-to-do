import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

import { ApiError, type UpdateStatus, type UpdateStep } from "../api/client";
import { useApi } from "../api/queries";
import { errorText } from "../ui/errors";

// Often enough to reload soon after the server is back, rare enough not to load it.
const POLL_INTERVAL_MS = 2_000;
// The backend says an update already runs: the run is going, just show it.
const ALREADY_RUNNING_STATUS = 409;

/** How an explicit check ended when the update window did not open. */
export type CheckOutcome = "latest" | "failed";

/** An update started from the app: going through its stages, or failed with the end of its log. */
export type UpdateRun = { phase: "running"; steps: UpdateStep[] } | { phase: "failed"; logTail: string };

export interface Updates {
  /** What the backend last said about releases; null until it answers. */
  status: UpdateStatus | null;
  checking: boolean;
  checkOutcome: CheckOutcome | null;
  offerOpen: boolean;
  run: UpdateRun | null;
  startError: string | null;
  /** Asks past the daily cache; the outcome when the update window did not open, else null. */
  checkNow: () => Promise<CheckOutcome | null>;
  openOffer: () => void;
  closeOffer: () => void;
  startUpdate: () => Promise<void>;
  dismissFailure: () => void;
}

const reloadPage = () => window.location.reload();

/**
 * What the copy knows about newer releases and how its update goes. While it runs the server is down:
 * failed polls mean "still updating". The server back on another version, or saying `done`, reloads
 * the page. A page opened in the middle of an update shows it again.
 */
export function useUpdatesController(reload: () => void = reloadPage): Updates {
  const api = useApi();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkOutcome, setCheckOutcome] = useState<CheckOutcome | null>(null);
  const [offerOpen, setOfferOpen] = useState(false);
  const [run, setRun] = useState<UpdateRun | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const versionBefore = useRef<string | null>(null);

  useEffect(() => {
    api.updates(false).then(setStatus, () => {});
    api.updateState().then(
      (state) => {
        if (state.state === "running") setRun({ phase: "running", steps: state.steps ?? [] });
      },
      () => {},
    );
  }, [api]);

  const checkNow = useCallback(async (): Promise<CheckOutcome | null> => {
    setChecking(true);
    setCheckOutcome(null);
    let outcome: CheckOutcome | null;
    try {
      const next = await api.updates(true);
      setStatus(next);
      outcome = next.available ? null : next.check_failed ? "failed" : "latest";
      if (next.available) setOfferOpen(true);
    } catch {
      outcome = "failed";
    }
    setCheckOutcome(outcome);
    setChecking(false);
    return outcome;
  }, [api]);

  const current = status?.current ?? null;
  const startUpdate = useCallback(async () => {
    setStartError(null);
    versionBefore.current = current;
    try {
      await api.startUpdate();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === ALREADY_RUNNING_STATUS)) {
        setStartError(errorText(error));
        return;
      }
    }
    setOfferOpen(false);
    setRun({ phase: "running", steps: [] });
  }, [api, current]);

  const running = run?.phase === "running";
  useEffect(() => {
    if (!running) return;
    const poll = async () => {
      const [state, version] = await Promise.allSettled([api.updateState(), api.version()]);
      const versionNow = version.status === "fulfilled" ? version.value.version : null;
      const changed = versionNow !== null && versionBefore.current !== null && versionNow !== versionBefore.current;
      if (changed || (state.status === "fulfilled" && state.value.state === "done")) reload();
      else if (state.status === "fulfilled" && state.value.state === "failed") setRun({ phase: "failed", logTail: state.value.log_tail ?? "" });
      else if (state.status === "fulfilled" && state.value.state === "running") setRun({ phase: "running", steps: state.value.steps ?? [] });
    };
    const timer = setInterval(() => void poll(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [api, running, reload]);

  return {
    status,
    checking,
    checkOutcome,
    offerOpen,
    run,
    startError,
    checkNow,
    openOffer: useCallback(() => setOfferOpen(true), []),
    closeOffer: useCallback(() => {
      setOfferOpen(false);
      setStartError(null);
    }, []),
    startUpdate,
    dismissFailure: useCallback(() => setRun(null), []),
  };
}

export const UpdatesContext = createContext<Updates | null>(null);

export function useUpdates(): Updates {
  const updates = useContext(UpdatesContext);
  if (!updates) throw new Error("useUpdates needs an UpdatesProvider");
  return updates;
}

export const CHECKING_TEXT = "Ищем новую версию…";
export const CHECK_FAILED_TEXT = "Не получилось проверить обновления. Попробуйте позже.";
export const latestVersionText = (version: string) => `У вас последняя версия, ${version}`;
