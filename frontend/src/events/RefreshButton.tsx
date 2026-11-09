import type { RefreshStatus } from "../api/client";
import { useRefresh } from "../api/queries";
import { Icon } from "../ui/Icon";
import "./RefreshButton.css";

const STAGE_LABEL: Record<RefreshStatus["stage"], (status?: RefreshStatus) => string> = {
  idle: () => "Собираю посты",
  collecting: () => "Собираю посты",
  reading: (s) => (s ? `Читаю посты: ${s.posts_read} из ${s.posts_to_read}` : "Читаю посты"),
  merging: () => "Склеиваю повторы",
  done: () => "Готово",
  failed: () => "Не получилось",
};

/** Starts a refresh, shows its stage while it runs and what went wrong when it ends. */
export function RefreshButton() {
  const refresh = useRefresh();
  const errors = refresh.running ? [] : (refresh.status?.errors ?? []);
  const label = refresh.running ? STAGE_LABEL[refresh.status?.stage ?? "collecting"](refresh.status) : "Обновить";
  return (
    <div className="refresh">
      <button type="button" className="button refresh__button" onClick={refresh.start} disabled={refresh.running} aria-busy={refresh.running} data-tip="Собрать новые посты из источников и разобрать их">
        <Icon name="refresh" size={16} strokeWidth={2.2} className={refresh.running ? "refresh__spin" : undefined} />
        {label}
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
