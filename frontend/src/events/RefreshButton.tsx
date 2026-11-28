import { useReaderSignInStatus, useRefresh, useSettings } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { READERS } from "../domain/readers";
import { refreshLabel, timeLeft } from "../domain/refresh";
import { Icon } from "../ui/Icon";
import { InlineCode } from "../ui/InlineCode";
import { ReaderSignIn } from "./ReaderSignIn";
import "./RefreshButton.css";

/** Starts a refresh, shows its stage while it runs and what went wrong when it ends. */
export function RefreshButton() {
  const refresh = useRefresh();
  const settings = useSettings();
  const knownProvider = refresh.status?.reader ?? settings.data?.llm_provider;
  const provider = knownProvider ?? "claude";
  const reader = READERS[provider];
  const finishedErrors = refresh.running ? [] : (refresh.status?.errors ?? []);
  const readerError = refresh.running ? null : (refresh.status?.reader_error ?? null);
  const boxWanted = readerError !== null && knownProvider !== undefined;
  const signIn = useReaderSignInStatus(provider, boxWanted);
  const boxKnows = boxWanted && signIn.data !== undefined && (reader.boxWhenSignInUnknown || signIn.data.state !== "unknown");
  const boxShown = reader.boxWhenSignInUnknown ? boxWanted : boxKnows;
  const errors = readerError !== null && !boxKnows ? [readerError, ...finishedErrors] : finishedErrors;
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
      {boxShown && <ReaderSignIn provider={provider} />}
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
