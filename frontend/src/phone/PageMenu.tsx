import { useEffect, useState } from "react";

import { ago } from "../domain/dates";
import { Icon } from "../ui/Icon";
import { Popover } from "../ui/Popover";
import { isStale, type PhoneSnapshot } from "./snapshot";

/** One small control among the filters: when the plans were published, in the warning colour once a day old, and Lock. */
export function PageMenu({ snapshot, now: clock, onLock }: { snapshot: PhoneSnapshot; now: () => Date; onLock: () => void }) {
  const now = useNow(clock);
  const stale = isStale(snapshot, now);
  const when = ago(snapshot.made_at, now);
  return (
    <Popover
      className="page-menu"
      trigger={(open, toggle) => (
        <button
          type="button"
          className={`chip page-menu__trigger${stale ? " page-menu__trigger--stale" : ""}`}
          aria-label={`Updated ${when}`}
          aria-expanded={open}
          onClick={toggle}
        >
          <Icon name={stale ? "alert" : "clock"} size={15} strokeWidth={2.2} />
        </button>
      )}
    >
      {() => (
        <div className="page-menu__body">
          <div className={`page-menu__updated${stale ? " page-menu__updated--stale" : ""}`} role="status">
            <span className="label">Updated</span>
            <span className="page-menu__when">{when}</span>
            {stale && <span className="page-menu__hint">The laptop may be asleep, so the plans may be out of date.</span>}
          </div>
          <div className="popover__footer">
            <button type="button" className="popover__item page-menu__lock" onClick={onLock}>
              <Icon name="lock" size={16} />
              Lock
            </button>
          </div>
        </div>
      )}
    </Popover>
  );
}

const TICK_MS = 60_000;

/** The current moment, looked at again every minute and whenever the page comes back to the foreground. */
function useNow(clock: () => Date): Date {
  const [now, setNow] = useState(clock);
  useEffect(() => {
    const look = () => setNow(clock());
    const onVisibility = () => document.visibilityState === "visible" && look();
    const timer = setInterval(look, TICK_MS);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [clock]);
  return now;
}
