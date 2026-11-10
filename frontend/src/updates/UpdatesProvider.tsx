import { useEffect, useState, type ReactNode } from "react";

import type { ChangelogEntry } from "../api/client";
import { useApi } from "../api/queries";
import { Modal } from "../ui/Modal";
import { ChangelogWindow } from "./ChangelogWindow";
import { UpdatingOverlay } from "./UpdatingOverlay";
import { CHECK_FAILED_TEXT, CHECKING_TEXT, latestVersionText, UpdatesContext, useUpdates, useUpdatesController, type CheckOutcome } from "./useUpdates";
import "./updates.css";

/** One state of updates for the whole app: the header, the settings and the macOS menu see the same. */
export function UpdatesProvider({ children, reload, onNativeCheck }: { children: ReactNode; reload?: () => void; onNativeCheck?: (listener: () => void) => () => void }) {
  const updates = useUpdatesController(reload);
  return (
    <UpdatesContext.Provider value={updates}>
      {children}
      <UpdateOffer />
      <UpdatingOverlay />
      <WhatsNew />
      {onNativeCheck && <NativeCheck subscribe={onNativeCheck} />}
    </UpdatesContext.Provider>
  );
}

/** The update window: what the new version brings and the button that installs it. */
function UpdateOffer() {
  const { status, offerOpen, closeOffer, startUpdate, startError } = useUpdates();
  if (!offerOpen || !status) return null;
  return (
    <ChangelogWindow
      mode="update"
      entries={status.entries}
      onClose={closeOffer}
      note={startError && <span className="error-text">{startError}</span>}
      action={
        <button type="button" className="button" onClick={() => void startUpdate()}>
          Обновить до {status.latest}
        </button>
      }
    />
  );
}

/** The first open after an update: the versions released since the last one seen. */
function WhatsNew() {
  const api = useApi();
  const [entries, setEntries] = useState<ChangelogEntry[]>([]);
  useEffect(() => {
    api.unseenChangelog().then(setEntries, () => {});
  }, [api]);
  if (entries.length === 0) return null;
  const close = () => {
    setEntries([]);
    api.markChangelogSeen().catch(() => {});
  };
  return <ChangelogWindow mode="whatsnew" entries={entries} onClose={close} />;
}

/** «Проверить обновления…» in the macOS app's menu: the check over the current screen. */
function NativeCheck({ subscribe }: { subscribe: (listener: () => void) => () => void }) {
  const { status, checkNow } = useUpdates();
  const [check, setCheck] = useState<"checking" | CheckOutcome | null>(null);
  useEffect(
    () =>
      subscribe(() => {
        setCheck("checking");
        void checkNow().then(setCheck);
      }),
    [subscribe, checkNow],
  );
  if (!check) return null;
  const close = () => setCheck(null);
  return (
    <Modal label="Проверка обновлений" onClose={close}>
      <div className="update-check">
        {check === "checking" ? (
          <p className="update-check__text">
            <span className="spinner" /> {CHECKING_TEXT}
          </p>
        ) : check === "failed" || !status ? (
          <p className="update-check__text error-text">{CHECK_FAILED_TEXT}</p>
        ) : (
          <p className="update-check__text">{latestVersionText(status.current)}</p>
        )}
      </div>
    </Modal>
  );
}

/** A quiet pill in the header while a newer release is out; it opens the update window. */
export function UpdateIndicator() {
  const { status, openOffer } = useUpdates();
  if (!status?.available) return null;
  return (
    <button type="button" className="update-pill" onClick={openOffer} data-tip={`Вышла версия ${status.latest}`}>
      Новая версия
    </button>
  );
}
