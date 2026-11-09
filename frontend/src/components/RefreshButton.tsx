import type { RefreshStatus } from "../api/client";
import { useRefresh } from "../api/hooks";
import { Icon } from "./Icon";
import "./RefreshButton.css";

function progressLabel(status: RefreshStatus | undefined): string {
  if (!status || status.stage === "collecting" || status.stage === "idle") return "Собираю посты";
  if (status.stage === "reading") return `Читаю посты: ${status.posts_read} из ${status.posts_to_read}`;
  return "Склеиваю повторы";
}

/** Starts a refresh, shows its stage while it runs and what went wrong when it ends. */
export function RefreshButton() {
  const refresh = useRefresh();
  const errors = !refresh.running ? (refresh.status?.errors ?? []) : [];
  return (
    <div className="refresh">
      <button type="button" className="refresh__button" onClick={refresh.start} disabled={refresh.running} aria-busy={refresh.running}>
        <Icon name="refresh" size={16} strokeWidth={2.2} className={refresh.running ? "refresh__spin" : undefined} />
        {refresh.running ? progressLabel(refresh.status) : "Обновить"}
      </button>
      {errors.length > 0 && (
        <div className="refresh__errors" role="status">
          {errors.map((error) => (
            <span key={error}>{error}</span>
          ))}
        </div>
      )}
    </div>
  );
}
