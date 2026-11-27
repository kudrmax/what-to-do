import { useRefresh } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { refreshLabel, timeLeft } from "../domain/refresh";
import { Icon } from "../ui/Icon";
import { InlineCode } from "../ui/InlineCode";
import { ClaudeSignIn } from "./ClaudeSignIn";
import "./RefreshButton.css";

/** The backend's own line for a missing login; the sign-in note below replaces it. */
const SIGN_IN_ERROR = "Sign in to Claude Code";

/** Starts a refresh, shows its stage while it runs and what went wrong when it ends. */
export function RefreshButton() {
  const refresh = useRefresh();
  const signedOut = !refresh.running && (refresh.status?.claude_unavailable ?? false);
  const errors = (refresh.running ? [] : (refresh.status?.errors ?? [])).filter((error) => !(signedOut && error.startsWith(SIGN_IN_ERROR)));
  const { city } = useActiveCity();
  const label = refresh.running ? refreshLabel(refresh.status) : "Refresh";
  const left = refresh.running ? timeLeft(refresh.status) : null;
  return (
    <div className="refresh">
      <button type="button" className="button refresh__button" onClick={refresh.start} disabled={refresh.running} aria-busy={refresh.running} data-tip={`Collect what’s new from the channels and websites of ${city?.name ?? "the city"}, and read it`}>
        <Icon name="refresh" size={16} strokeWidth={2.2} className={refresh.running ? "refresh__spin" : undefined} />
        {label}
        {left && <span className="refresh__left">{left}</span>}
      </button>
      {signedOut && <ClaudeSignIn />}
      {errors.length > 0 && (
        <div className="note refresh__errors" role="status">
          {errors.map((error) => (
            <span key={error}>
              <InlineCode text={error} />
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
