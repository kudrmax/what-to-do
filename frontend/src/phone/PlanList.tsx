import { useCallback, useState } from "react";

import { ago, dayHeading } from "../domain/dates";
import { groupByDay } from "../domain/feed";
import { SHOWN_PLANS } from "../domain/plans";
import { ToggleChip } from "../ui/Chips";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { EventSheet } from "./EventSheet";
import { PhoneCard } from "./PhoneCard";
import { isStale, type PhoneOccurrence, type PhoneSnapshot } from "./snapshot";

/** The Plans screen of the app, upcoming, as it was when the snapshot was made. */
export function PlanList({ snapshot, now, onLock }: { snapshot: PhoneSnapshot; now: Date; onLock: () => void }) {
  const [onlySure, setOnlySure] = useState(false);
  const [opened, setOpened] = useState<PhoneOccurrence | null>(null);
  const close = useCallback(() => setOpened(null), []);
  const plans: string[] = onlySure ? SHOWN_PLANS.sure : SHOWN_PLANS.going;
  const shown = snapshot.occurrences.filter((item) => plans.includes(item.event.plan ?? "none"));

  return (
    <div className="phone">
      <header className="phone-header">
        <div className="phone-header__row">
          <div className="phone-header__titles">
            <h1 className="title">Plans</h1>
            <span className="phone-header__city">
              <Icon name="pin" size={14} />
              {snapshot.city}
            </span>
          </div>
          <Updated snapshot={snapshot} now={now} />
          <IconButton icon="lock" label="Lock" className="phone-header__lock" onClick={onLock} />
        </div>
        <div className="phone-header__chips">
          <ToggleChip label="Only “Going for sure”" on={onlySure} onChange={setOnlySure} />
        </div>
      </header>

      <main className="phone-list">
        {shown.length === 0 ? (
          <div className="empty">
            <p className="empty__title">No plans yet</p>
            <p className="empty__text">{onlySure ? "Nothing is marked “Going for sure” yet." : "Mark an event as “Maybe going” or “Going for sure” in What To Do and it will appear here."}</p>
          </div>
        ) : (
          <div className="day-feed">
            {groupByDay(shown).map(([day, items]) => {
              const heading = dayHeading(day, snapshot.today);
              return (
                <section key={day} className="day-feed__day" aria-label={heading.title}>
                  <h2 className="day-heading">
                    <span className="section-title">{heading.title}</span>
                    <span className="day-heading__sub">{heading.subtitle}</span>
                  </h2>
                  <div className="phone-list__cards">
                    {items.map((item) => (
                      <PhoneCard key={`${item.event.id}-${day}`} event={item.event} tags={snapshot.tags} onOpen={() => setOpened(item)} />
                    ))}
                  </div>
                </section>
              );
            })}
          </div>
        )}
      </main>

      {opened && <EventSheet occurrence={opened} tags={snapshot.tags} onClose={close} />}
    </div>
  );
}

/** When the snapshot was made; in the warning color once it is more than a day old. */
function Updated({ snapshot, now }: { snapshot: PhoneSnapshot; now: Date }) {
  const stale = isStale(snapshot, now);
  return (
    <div className={`phone-updated${stale ? " phone-updated--stale" : ""}`} role="status">
      <span className="phone-updated__label">
        {stale && <Icon name="alert" size={13} />}
        Updated
      </span>
      <span className="phone-updated__time">{ago(snapshot.made_at, now)}</span>
    </div>
  );
}
