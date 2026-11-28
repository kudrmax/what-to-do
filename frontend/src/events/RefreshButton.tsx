import { useReaderSignInStatus, useRefresh, useSettings } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { plural } from "../domain/dates";
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
  const postsLeft = refresh.running || refresh.status?.limit == null ? null : (refresh.status.posts_left ?? null);
  const { city } = useActiveCity();
  const shortLimit = settings.data?.partial_refresh_posts;
  return (
    <div className="refresh">
      <div className="refresh__buttons">
        <RefreshAction
          label="Refresh"
          tip={`Collect what’s new from the channels and websites of ${city?.name ?? "the city"}, and read it`}
          busy={refresh.running && refresh.runningLimit === null}
          refresh={refresh}
          onClick={() => refresh.start()}
        />
        {shortLimit !== undefined && (
          <RefreshAction
            label={`Refresh ${shortLimit}`}
            tip={`Collect what’s new from every source, but read only the next ${shortLimit} posts, top to bottom in your source order`}
            busy={refresh.running && refresh.runningLimit !== null}
            refresh={refresh}
            quiet
            onClick={() => refresh.start(shortLimit)}
          />
        )}
      </div>
      {postsLeft !== null && <p className="refresh__posts-left">{postsLeftText(postsLeft)}</p>}
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

type Refresh = ReturnType<typeof useRefresh>;

/** One way to refresh; the one that started the running refresh shows its stage, every one waits for it to end. */
function RefreshAction({ label, tip, busy, quiet = false, refresh, onClick }: { label: string; tip: string; busy: boolean; quiet?: boolean; refresh: Refresh; onClick: () => void }) {
  const left = busy ? timeLeft(refresh.status) : null;
  const classes = ["button", "refresh__button", quiet && "button--quiet", busy && "refresh__button--busy"].filter(Boolean).join(" ");
  return (
    <button type="button" className={classes} onClick={onClick} disabled={refresh.running} aria-busy={busy} data-tip={tip}>
      <Icon name="refresh" size={16} strokeWidth={2.2} className={busy ? "refresh__spin" : undefined} />
      {busy ? refreshLabel(refresh.status) : label}
      {left && <span className="refresh__left">{left}</span>}
    </button>
  );
}

function postsLeftText(count: number): string {
  return count === 0 ? "All posts are read" : `${count} ${plural(count, "post", "posts")} left to read`;
}
