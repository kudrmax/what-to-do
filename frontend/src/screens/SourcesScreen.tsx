import { useId, useState, type FormEvent } from "react";

import type { InstagramReading, SitePreview, Source, SourceKind } from "../api/client";
import { useAddSource, useDeleteSource, useMarkSource, usePauseSource, usePreviewSource, useRenameSource, useSetInstagramReading, useSources } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { ago, clock, longDate, plural } from "../domain/dates";
import { ambiguousName } from "../domain/sources";
import { errorText } from "../ui/errors";
import { Icon, type IconName } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { InlineEdit } from "../ui/InlineEdit";
import { Screen } from "../ui/Screen";
import { Segmented, type SegmentedOption } from "../ui/Segmented";
import { FindingSources } from "./FindingSources";
import { InstagramPreviewCard } from "./InstagramPreviewCard";
import { NoCity } from "./NoCity";
import { PotentialSources } from "./PotentialSources";
import "./SourcesScreen.css";

export function SourcesScreen() {
  const { city } = useActiveCity();
  return (
    <Screen title={SECTIONS.sources.title} narrow>
      {city ? (
        <>
          <AddSourceForm />
          <SourceList />
          <PotentialSources />
        </>
      ) : (
        <NoCity />
      )}
    </Screen>
  );
}

const NETWORKS: SegmentedOption<SourceKind>[] = [
  { id: "telegram", label: "Telegram" },
  { id: "instagram", label: "Instagram" },
];

export function AddSourceForm() {
  const check = usePreviewSource();
  const add = useAddSource();
  const [link, setLink] = useState("");
  const [title, setTitle] = useState("");
  const [network, setNetwork] = useState<SourceKind | null>(null);
  const [preview, setPreview] = useState<SitePreview | null>(null);
  const asksNetwork = ambiguousName(link);
  const kind = asksNetwork ? network : null;
  const reset = () => (setLink(""), setTitle(""), setNetwork(null), setPreview(null), check.reset());
  const addNow = (instagram?: InstagramReading) =>
    add.mutate({ link: link.trim(), title: title.trim() || null, ...(kind && { kind }), ...(instagram && { instagram }) }, { onSuccess: reset });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.reset();
    setPreview(null);
    check.mutate({ link: link.trim(), ...(kind && { kind }) }, { onSuccess: (found) => (found.kind === "telegram" ? addNow() : setPreview(found)) });
  };
  const changeLink = (value: string) => (setLink(value), setNetwork(null), setPreview(null));
  const busy = check.isPending || add.isPending;
  const unchosen = asksNetwork && !network;
  const error = check.error ?? add.error;
  return (
    <div className="add-source-block">
      <form className="add-source" onSubmit={submit}>
        <label className="add-source__field add-source__field--wide">
          <span className="label">Link</span>
          <input
            className="input"
            value={link}
            onChange={(e) => changeLink(e.target.value)}
            placeholder="Link or @name"
            required
            aria-invalid={Boolean(error)}
          />
        </label>
        {asksNetwork && (
          <div className="add-source__field add-source__network">
            <span className="label" aria-hidden="true">
              Network
            </span>
            <Segmented label="Network" options={NETWORKS} value={network} onChange={setNetwork} role="radio" />
          </div>
        )}
        <label className="add-source__field">
          <span className="label">Name</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Its own name" />
        </label>
        {!preview && (
          <button type="submit" className="button" disabled={busy || !link.trim() || unchosen} title={unchosen ? "Choose Telegram or Instagram first" : undefined}>
            {busy ? "Checking…" : "Add"}
          </button>
        )}
        {error && <p className="error-text add-source__error">{errorText(error)}</p>}
      </form>
      {preview?.kind === "web" && <SitePreviewCard site={preview} adding={add.isPending} onAdd={() => addNow()} onCancel={() => setPreview(null)} />}
      {preview?.kind === "instagram" && <InstagramPreviewCard profile={preview} adding={add.isPending} onAdd={addNow} onCancel={() => setPreview(null)} />}
    </div>
  );
}

function SitePreviewCard({ site, adding, onAdd, onCancel }: { site: SitePreview; adding: boolean; onAdd: () => void; onCancel: () => void }) {
  const titleId = useId();
  const found = site.pages_found;
  return (
    <section className="site-preview" aria-labelledby={titleId}>
      <header className="site-preview__header">
        <span className="site-preview__icon">
          <Icon name="globe" size={20} />
        </span>
        <div className="site-preview__name">
          <h3 id={titleId} className="site-preview__title">
            {site.title}
          </h3>
          <a href={`https://${site.handle}`} target="_blank" rel="noreferrer" className="site-preview__link">
            {site.handle}
          </a>
        </div>
      </header>
      <div className="site-preview__found">
        <p className="site-preview__count">
          {found} {plural(found, "event", "events")} on the website
        </p>
        <p className="site-preview__scope">The app will get events in your city for the next 30 days</p>
      </div>
      {site.examples.length > 0 && (
        <ul className="site-preview__examples" aria-label="Examples">
          {site.examples.map((example) => (
            <li key={example.url} className="site-preview__example">
              <a href={example.url} target="_blank" rel="noreferrer" className="site-preview__event">
                {example.title}
              </a>
              <span className="site-preview__when">
                <span>{longDate(example.day)}</span>
                {example.time && <span className="site-preview__time">{clock(example.time)}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <footer className="site-preview__actions">
        <button type="button" className="button button--quiet" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button" onClick={onAdd} disabled={adding}>
          {adding ? "Adding…" : "Add website"}
        </button>
      </footer>
    </section>
  );
}

export function SourceList() {
  const sources = useSources();
  const { city } = useActiveCity();
  if (sources.data?.length === 0 && city) return <FindingSources city={city.name} />;
  if (!sources.data?.length) return null;
  return (
    <div className="sources-table" role="table" aria-label="Sources">
      {favoritesFirst(sources.data).map((source) => (
        <SourceRow key={source.id} source={source} />
      ))}
    </div>
  );
}

function favoritesFirst(sources: Source[]): Source[] {
  return [...sources].sort((a, b) => Number(b.status === "favorite") - Number(a.status === "favorite"));
}

function FavoriteToggle({ source }: { source: Source }) {
  const mark = useMarkSource();
  const favorite = source.status === "favorite";
  return (
    <IconButton
      icon="star"
      label={favorite ? "Remove from favorites" : "Add to favorites"}
      aria-pressed={favorite}
      className={`favorite-toggle${favorite ? " favorite-toggle--on" : ""}`}
      onClick={() => mark.mutate({ id: source.id, status: favorite ? "new" : "favorite" })}
    />
  );
}

function PauseToggle({ source }: { source: Source }) {
  const pause = usePauseSource();
  return (
    <IconButton
      icon={source.paused ? "play" : "pause"}
      label={source.paused ? "Resume: read new posts again" : "Pause: stop reading new posts, hide its unmarked events"}
      onClick={() => pause.mutate({ id: source.id, paused: !source.paused })}
    />
  );
}

function sourceState(source: Source): { label: string; kind: string } {
  if (source.paused) return { label: "Paused", kind: "paused" };
  if (source.last_error) return { label: source.last_error, kind: "error" };
  return source.last_refreshed_at ? { label: "Working", kind: "ok" } : { label: "Awaiting refresh", kind: "new" };
}

const KINDS: Record<SourceKind, { label: string; icon: IconName; address: (source: Source) => string }> = {
  telegram: { label: "Telegram channel", icon: "send", address: (source) => `@${source.handle}` },
  web: { label: "Website", icon: "globe", address: (source) => source.handle },
  instagram: { label: "Instagram profile", icon: "instagram", address: (source) => `@${source.handle}` },
};

function InstagramReadingToggles({ source, reading }: { source: Source; reading: InstagramReading }) {
  const set = useSetInstagramReading();
  const shown = set.isPending ? set.variables.reading : reading;
  const toggle = (change: Partial<InstagramReading>) => set.mutate({ id: source.id, reading: { ...shown, ...change } });
  return (
    <>
      <div className="reading-toggles" role="group" aria-label="What to read">
        <ReadingToggle name="Posts" on={shown.posts} last={shown.posts && !shown.stories} onChange={(posts) => toggle({ posts })} />
        <ReadingToggle name="Pinned stories" on={shown.stories} last={shown.stories && !shown.posts} onChange={(stories) => toggle({ stories })} />
      </div>
      {set.error && <p className="error-text">{errorText(set.error)}</p>}
    </>
  );
}

function ReadingToggle({ name, on, last, onChange }: { name: string; on: boolean; last: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className={`reading-toggle${on ? " reading-toggle--on" : ""}`} title={last ? "A profile reads at least one of them" : undefined}>
      <input type="checkbox" checked={on} disabled={last} onChange={(e) => onChange(e.target.checked)} />
      {name}
    </label>
  );
}

function SourceRow({ source }: { source: Source }) {
  const rename = useRenameSource();
  const remove = useDeleteSource();
  const [confirming, setConfirming] = useState(false);
  const kind = KINDS[source.kind];
  const state = sourceState(source);
  return (
    <div className={`sources-table__row${source.paused ? " sources-table__row--paused" : ""}`} role="row">
      <span role="cell" className="sources-table__favorite">
        <FavoriteToggle source={source} />
      </span>
      <div className="sources-table__name" role="cell">
        <span className="sources-table__heading">
          <span role="img" aria-label={kind.label} className="sources-table__kind">
            <Icon name={kind.icon} size={14} />
          </span>
          <InlineEdit value={source.title} label="Source name" className="sources-table__title" onSave={(title) => rename.mutate({ id: source.id, title })} />
        </span>
        <a href={source.url} target="_blank" rel="noreferrer" className="sources-table__link">
          {kind.address(source)}
        </a>
        {source.instagram && <InstagramReadingToggles source={source} reading={source.instagram} />}
      </div>
      <span role="cell" className="sources-table__value sources-table__updated">
        {source.last_refreshed_at ? `Refreshed ${ago(source.last_refreshed_at)}` : "Not refreshed yet"}
      </span>
      <span role="cell" className="sources-table__value sources-table__count">
        {source.events_found} {plural(source.events_found, "event", "events")}
      </span>
      <span role="cell" className="sources-table__state">
        <span className={`state state--${state.kind}`}>{state.label}</span>
      </span>
      <span role="cell" className="sources-table__actions">
        {confirming ? (
          <>
            <button type="button" className="button button--small button--danger" onClick={() => remove.mutate(source.id)}>
              Delete
            </button>
            <button type="button" className="button button--small button--quiet" onClick={() => setConfirming(false)}>
              No
            </button>
          </>
        ) : (
          <>
            <PauseToggle source={source} />
            <IconButton icon="trash" label="Delete source and its events" onClick={() => setConfirming(true)} />
          </>
        )}
      </span>
    </div>
  );
}
