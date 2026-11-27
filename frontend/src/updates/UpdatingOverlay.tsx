import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";

import type { UpdateStep } from "../api/client";
import { CommandLine } from "../ui/CommandLine";
import { Icon } from "../ui/Icon";
import { desktopOf, TERMINAL_STEPS } from "./terminal";
import { useUpdates } from "./useUpdates";
import "./updates.css";

const STUCK_AFTER_MINUTES = 10;

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
        <div className="updating__card" role="alertdialog" aria-modal="true" aria-label="Updating the app">
          <div className="updating__progress">
            {run.steps.length === 0 && <span className="spinner" />}
            Updating the app…
          </div>
          {run.steps.length > 0 && <UpdateSteps steps={run.steps} />}
          {status?.restart_command && (
            <div className="updating__fallback">
              <p className="updating__hint">Nothing has changed for {STUCK_AFTER_MINUTES} minutes? Restart the app manually:</p>
              <ByHand command={status.restart_command} waitFor="Wait for the line that starts with →." />
            </div>
          )}
          {status && !status.restart_command && (
            <p className="updating__fallback updating__hint">Nothing has changed for {STUCK_AFTER_MINUTES} minutes? Quit What To Do and open it again.</p>
          )}
        </div>
      ) : (
        <UpdateFailed logTail={run.logTail} command={status?.update_command ?? null} downloadPage={status?.download_page ?? null} onClose={dismissFailure} />
      )}
    </div>,
    document.body,
  );
}

function UpdateSteps({ steps }: { steps: UpdateStep[] }) {
  return (
    <ol className="updating__steps" aria-label="Update steps">
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

function UpdateFailed({ logTail, command, downloadPage, onClose }: { logTail: string; command: string | null; downloadPage: string | null; onClose: () => void }) {
  const log = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [logTail]);
  return (
    <div className="updating__card" role="alertdialog" aria-modal="true" aria-label="Update failed">
      <h2 className="updating__title">Update failed</h2>
      {logTail && (
        <pre ref={log} className="updating__log">
          {logTail}
        </pre>
      )}
      {command && (
        <div className="updating__fallback">
          <p className="updating__hint">Run the update manually to see what went wrong:</p>
          <ByHand command={command} waitFor="Wait for the line “Updated to …” or an error." />
        </div>
      )}
      {!command && downloadPage && (
        <div className="updating__fallback">
          <p className="updating__hint">Install the new version the way you installed this one: download the disk image for your Mac, open it and drag What To Do to Applications. Your events and settings stay.</p>
          <a className="button button--small" href={downloadPage} target="_blank" rel="noreferrer">
            Open the download page
          </a>
        </div>
      )}
      <div className="updating__footer">
        <button type="button" className="button button--quiet" onClick={onClose}>
          Close
        </button>
      </div>
    </div>
  );
}

/** For someone who never opened a terminal: where it is on this computer, where the command goes, what to wait for. */
function ByHand({ command, waitFor }: { command: string; waitFor: string }) {
  const steps = TERMINAL_STEPS[desktopOf(navigator.userAgent)];
  return (
    <ol className="updating__by-hand">
      <li>{steps.open}</li>
      <li>
        {steps.paste}
        <CommandLine command={command} />
      </li>
      <li>{waitFor} Then reload this page.</li>
    </ol>
  );
}
