import { useRefresh } from "../api/queries";
import { refreshLabel, timeLeft } from "../domain/refresh";
import { Icon } from "../ui/Icon";
import "./RefreshButton.css";

/** Starts a refresh, shows its stage while it runs and what went wrong when it ends. */
export function RefreshButton() {
  const refresh = useRefresh();
  const errors = refresh.running ? [] : (refresh.status?.errors ?? []);
  const label = refresh.running ? refreshLabel(refresh.status) : "Refresh";
  const left = refresh.running ? timeLeft(refresh.status) : null;
  return (
    <div className="refresh">
      <button type="button" className="button refresh__button" onClick={refresh.start} disabled={refresh.running} aria-busy={refresh.running} data-tip="Collect what’s new from channels and websites and read it">
        <Icon name="refresh" size={16} strokeWidth={2.2} className={refresh.running ? "refresh__spin" : undefined} />
        {label}
        {left && <span className="refresh__left">{left}</span>}
      </button>
      {errors.length > 0 && (
        <div className="note refresh__errors" role="status">
          {errors.map((error) => (
            <span key={error}>{error}</span>
          ))}
        </div>
      )}
    </div>
  );
}
