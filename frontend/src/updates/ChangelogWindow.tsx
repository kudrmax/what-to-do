import type { ReactNode } from "react";

import type { ChangelogEntry } from "../api/client";
import { Modal } from "../ui/Modal";
import "./updates.css";

/** update — what an update brings; whatsnew — what came out since the last look; history — all of it. */
export type ChangelogMode = "update" | "whatsnew" | "history";

const TITLES: Record<ChangelogMode, string> = {
  update: "Вышла новая версия",
  whatsnew: "Что нового",
  history: "История изменений",
};

const RELEASE_DAY = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" });

const releaseDay = (isoDay: string) => RELEASE_DAY.format(new Date(`${isoDay}T00:00:00`));

/** Releases the way the Obsidian changelog shows them: version and day, the summary, the sections. */
export function ChangelogWindow({ mode, entries, onClose, action, note }: { mode: ChangelogMode; entries: ChangelogEntry[]; onClose: () => void; action?: ReactNode; note?: ReactNode }) {
  return (
    <Modal label={TITLES[mode]} onClose={onClose}>
      <div className="changelog">
        <h1 className="changelog__title">{TITLES[mode]}</h1>
        {entries.length === 0 && <p className="changelog__empty">Изменений пока не записано</p>}
        {entries.map((entry) => (
          <article key={entry.version} className="changelog__entry">
            <header className="changelog__heading">
              <h2 className="changelog__version">{entry.version}</h2>
              <time className="changelog__day" dateTime={entry.released_on}>
                {releaseDay(entry.released_on)}
              </time>
            </header>
            {entry.summary && <p className="changelog__summary">{entry.summary}</p>}
            {entry.sections.map((section) => (
              <section key={section.title} className="changelog__section">
                <h3 className="changelog__section-title">{section.title}</h3>
                {/* The backend renders the repository's CHANGELOG.md with raw HTML switched off. */}
                <div className="changelog__body" dangerouslySetInnerHTML={{ __html: section.html }} />
              </section>
            ))}
          </article>
        ))}
        {(action || note) && (
          <footer className="changelog__footer">
            {note}
            {action}
          </footer>
        )}
      </div>
    </Modal>
  );
}
