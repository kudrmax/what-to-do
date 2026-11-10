import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { UpdateStep } from "../api/client";
import { Icon } from "../ui/Icon";
import { useUpdates } from "./useUpdates";
import "./updates.css";

const STUCK_AFTER_MINUTES = 10;
const COPY_LABELS = { idle: "Скопировать", copied: "Скопировано", failed: "Не скопировалось" } as const;

/** While the update runs the app under it is closed; a failed one says what to do by hand. */
export function UpdatingOverlay() {
  const { run, status, dismissFailure } = useUpdates();
  const running = run?.phase === "running";

  useEffect(() => {
    if (!running) return;
    const swallow = (event: KeyboardEvent) => {
      event.stopPropagation();
      event.preventDefault();
    };
    window.addEventListener("keydown", swallow, true);
    return () => window.removeEventListener("keydown", swallow, true);
  }, [running]);

  if (!run) return null;
  return createPortal(
    <div className="updating">
      {run.phase === "running" ? (
        <div className="updating__card" role="alertdialog" aria-modal="true" aria-label="Приложение обновляется">
          <div className="updating__progress">
            {run.steps.length === 0 && <span className="spinner" />}
            Приложение обновляется…
          </div>
          {run.steps.length > 0 && <UpdateSteps steps={run.steps} />}
          {status && (
            <div className="updating__fallback">
              <p className="updating__hint">Ничего не меняется {STUCK_AFTER_MINUTES} минут? Перезапустите приложение вручную:</p>
              <ByHand command={status.restart_command} waitFor="Дождитесь строки, которая начинается с →." />
            </div>
          )}
        </div>
      ) : (
        <UpdateFailed logTail={run.logTail} command={status?.update_command ?? null} onClose={dismissFailure} />
      )}
    </div>,
    document.body,
  );
}

function UpdateSteps({ steps }: { steps: UpdateStep[] }) {
  return (
    <ol className="updating__steps" aria-label="Этапы обновления">
      {steps.map((step, index) => (
        <li key={index} className="updating__step" data-status={step.status}>
          <span className="updating__mark">
            {step.status === "current" && <span className="spinner" />}
            {step.status === "done" && <Icon name="check" size={16} />}
            {step.status === "failed" && <Icon name="cross" size={16} />}
          </span>
          {step.title}
        </li>
      ))}
    </ol>
  );
}

function UpdateFailed({ logTail, command, onClose }: { logTail: string; command: string | null; onClose: () => void }) {
  const log = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [logTail]);
  return (
    <div className="updating__card" role="alertdialog" aria-modal="true" aria-label="Обновление не удалось">
      <h2 className="updating__title">Обновление не удалось</h2>
      {logTail && (
        <pre ref={log} className="updating__log">
          {logTail}
        </pre>
      )}
      {command && (
        <div className="updating__fallback">
          <p className="updating__hint">Запустите обновление вручную, чтобы увидеть, что пошло не так:</p>
          <ByHand command={command} waitFor="Дождитесь строки «Updated to …» или ошибки." />
        </div>
      )}
      <div className="updating__footer">
        <button type="button" className="button button--quiet" onClick={onClose}>
          Закрыть
        </button>
      </div>
    </div>
  );
}

/** For someone who never opened a terminal: where it is, where the command goes, what to wait for. */
function ByHand({ command, waitFor }: { command: string; waitFor: string }) {
  return (
    <ol className="updating__by-hand">
      <li>
        Откройте Терминал: нажмите <kbd>⌘</kbd> <kbd>Пробел</kbd>, наберите <b>Терминал</b> и нажмите <kbd>Return</kbd>.
      </li>
      <li>
        Нажмите <b>Скопировать</b>, щёлкните в окне Терминала, нажмите <kbd>⌘</kbd> <kbd>V</kbd> и <kbd>Return</kbd>.
        <CommandLine command={command} />
      </li>
      <li>{waitFor} Потом перезагрузите эту страницу.</li>
    </ol>
  );
}

function CommandLine({ command }: { command: string }) {
  const [copy, setCopy] = useState<keyof typeof COPY_LABELS>("idle");
  const copyCommand = () => {
    navigator.clipboard.writeText(command).then(
      () => setCopy("copied"),
      () => setCopy("failed"),
    );
  };
  return (
    <div className="updating__command">
      <code>{command}</code>
      <button type="button" className="button button--small" onClick={copyCommand}>
        {COPY_LABELS[copy]}
      </button>
    </div>
  );
}
