import { useId, useState, type FormEvent } from "react";

import type { SitePreview, Source } from "../api/client";
import { useAddSource, useDeleteSource, useMarkSource, usePreviewSource, useRenameSource, useSources } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { ago, longDate, plural } from "../domain/dates";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { InlineEdit } from "../ui/InlineEdit";
import { Screen } from "../ui/Screen";
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

export function AddSourceForm() {
  const check = usePreviewSource();
  const add = useAddSource();
  const [link, setLink] = useState("");
  const [title, setTitle] = useState("");
  const [site, setSite] = useState<SitePreview | null>(null);
  const reset = () => (setLink(""), setTitle(""), setSite(null), check.reset());
  const addNow = () => add.mutate({ link: link.trim(), title: title.trim() || null }, { onSuccess: reset });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.reset();
    setSite(null);
    check.mutate(link.trim(), { onSuccess: (preview) => (preview.kind === "web" ? setSite(preview) : addNow()) });
  };
  const busy = check.isPending || add.isPending;
  const error = check.error ?? add.error;
  return (
    <div className="add-source-block">
      <form className="add-source" onSubmit={submit}>
        <label className="add-source__field add-source__field--wide">
          <span className="label">Ссылка</span>
          <input
            className="input"
            value={link}
            onChange={(e) => (setLink(e.target.value), setSite(null))}
            placeholder="t.me/канал или страница события на сайте"
            required
            aria-invalid={Boolean(error)}
          />
        </label>
        <label className="add-source__field">
          <span className="label">Название</span>
          <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Как у канала или сайта" />
        </label>
        {!site && (
          <button type="submit" className="button" disabled={busy || !link.trim()}>
            {busy ? "Проверяю…" : "Добавить"}
          </button>
        )}
        {error && <p className="error-text add-source__error">{errorText(error)}</p>}
      </form>
      {site && <SitePreviewCard site={site} adding={add.isPending} onAdd={addNow} onCancel={() => setSite(null)} />}
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
      <p className="site-preview__found">
        {plural(found, "Найдена", "Найдено", "Найдено")} {found} {plural(found, "страница", "страницы", "страниц")} событий
      </p>
      {site.examples.length > 0 && (
        <ul className="site-preview__examples" aria-label="Например">
          {site.examples.map((example) => (
            <li key={example.url} className="site-preview__example">
              <a href={example.url} target="_blank" rel="noreferrer" className="site-preview__event">
                {example.title}
              </a>
              <span className="site-preview__when">
                <span>{longDate(example.day)}</span>
                {example.time && <span className="site-preview__time">{example.time}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      <footer className="site-preview__actions">
        <button type="button" className="button button--quiet" onClick={onCancel}>
          Отмена
        </button>
        <button type="button" className="button" onClick={onAdd} disabled={adding}>
          {adding ? "Добавляю…" : "Добавить сайт"}
        </button>
      </footer>
    </section>
  );
}

export function SourceList() {
  const sources = useSources();
  if (!sources.data?.length) {
    return <p className="muted">Источников пока нет. Добавьте Telegram-канал или сайт с афишей и нажмите «Обновить» в «Ближайших».</p>;
  }
  return (
    <div className="sources-table" role="table" aria-label="Источники">
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
      label={favorite ? "Убрать из избранного" : "В избранное"}
      aria-pressed={favorite}
      className={`favorite-toggle${favorite ? " favorite-toggle--on" : ""}`}
      onClick={() => mark.mutate({ id: source.id, status: favorite ? "new" : "favorite" })}
    />
  );
}

function SourceRow({ source }: { source: Source }) {
  const rename = useRenameSource();
  const remove = useDeleteSource();
  const [confirming, setConfirming] = useState(false);
  const web = source.kind === "web";
  const state = source.last_error
    ? { label: source.last_error, kind: "error" }
    : source.last_refreshed_at
      ? { label: "Работает", kind: "ok" }
      : { label: "Ждёт обновления", kind: "new" };
  return (
    <div className="sources-table__row" role="row">
      <span role="cell" className="sources-table__favorite">
        <FavoriteToggle source={source} />
      </span>
      <div className="sources-table__name" role="cell">
        <span className="sources-table__heading">
          <span role="img" aria-label={web ? "Сайт" : "Telegram-канал"} className="sources-table__kind">
            <Icon name={web ? "globe" : "send"} size={14} />
          </span>
          <InlineEdit value={source.title} label="Название источника" className="sources-table__title" onSave={(title) => rename.mutate({ id: source.id, title })} />
        </span>
        <a href={source.url} target="_blank" rel="noreferrer" className="sources-table__link">
          {web ? source.handle : `@${source.handle}`}
        </a>
      </div>
      <span role="cell" className="sources-table__value sources-table__updated">
        {source.last_refreshed_at ? `Обновлён ${ago(source.last_refreshed_at)}` : "Ещё не обновлялся"}
      </span>
      <span role="cell" className="sources-table__value sources-table__count">
        {source.events_found} {plural(source.events_found, "событие", "события", "событий")}
      </span>
      <span role="cell" className="sources-table__state">
        <span className={`state state--${state.kind}`}>{state.label}</span>
      </span>
      <span role="cell" className="sources-table__actions">
        {confirming ? (
          <>
            <button type="button" className="button button--small button--danger" onClick={() => remove.mutate(source.id)}>
              Удалить
            </button>
            <button type="button" className="button button--small button--quiet" onClick={() => setConfirming(false)}>
              Нет
            </button>
          </>
        ) : (
          <IconButton icon="trash" label="Удалить источник и его события" onClick={() => setConfirming(true)} />
        )}
      </span>
    </div>
  );
}
