import { useState } from "react";

import type { ChangelogEntry } from "../api/client";
import { useApi } from "../api/queries";
import { errorText } from "../ui/errors";
import { Section } from "../ui/Screen";
import { ChangelogWindow } from "./ChangelogWindow";
import { CHECK_FAILED_TEXT, latestVersionText, useUpdates } from "./useUpdates";

/** The settings' part about the app itself: its version, the changelog, a check for a new one. */
export function UpdatesSection() {
  const api = useApi();
  const updates = useUpdates();
  const [history, setHistory] = useState<ChangelogEntry[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const { status, checkOutcome } = updates;

  const openHistory = () => {
    setHistoryError(null);
    api.changelog().then(setHistory, (error) => setHistoryError(errorText(error)));
  };

  return (
    <Section title="Приложение">
      <div className="setting-row">
        <div className="setting-row__text">
          <span className="setting-row__label">Версия {status?.current ?? "…"}</span>
          <p className="setting-row__hint">
            {historyError ? (
              <span className="error-text">{historyError}</span>
            ) : checkOutcome === "failed" ? (
              <span className="error-text">{CHECK_FAILED_TEXT}</span>
            ) : status?.available ? (
              `Вышла версия ${status.latest}`
            ) : checkOutcome === "latest" && status ? (
              latestVersionText(status.current)
            ) : (
              "Раз в день приложение само проверяет, не вышла ли новая версия."
            )}
          </p>
        </div>
        <div className="setting-row__control setting-row__control--buttons">
          <button type="button" className="button button--quiet button--small" onClick={openHistory}>
            История изменений
          </button>
          {status?.available ? (
            <button type="button" className="button button--small" onClick={updates.openOffer}>
              Обновить до {status.latest}
            </button>
          ) : (
            <button type="button" className="button button--small" disabled={updates.checking} onClick={() => void updates.checkNow()}>
              {updates.checking ? "Проверяю…" : "Проверить обновления"}
            </button>
          )}
        </div>
      </div>
      {history && <ChangelogWindow mode="history" entries={history} onClose={() => setHistory(null)} />}
    </Section>
  );
}
