import { useState, type FormEvent } from "react";

import type { Source } from "../api/client";
import { useAddSource, useDeleteSource, useRenameSource, useSources } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { ago, plural } from "../domain/dates";
import { errorText } from "../ui/errors";
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

function AddSourceForm() {
  const add = useAddSource();
  const [link, setLink] = useState("");
  const [title, setTitle] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate({ link: link.trim(), title: title.trim() || null }, { onSuccess: () => (setLink(""), setTitle("")) });
  };
  return (
    <form className="add-source" onSubmit={submit}>
      <label className="add-source__field add-source__field--wide">
        <span className="label">Ссылка на публичный Telegram-канал</span>
        <input className="input" value={link} onChange={(e) => setLink(e.target.value)} placeholder="t.me/канал" required aria-invalid={add.isError} />
      </label>
      <label className="add-source__field">
        <span className="label">Название</span>
        <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Как в Telegram" />
      </label>
      <button type="submit" className="button" disabled={add.isPending || !link.trim()}>
        {add.isPending ? "Проверяю…" : "Добавить"}
      </button>
      {add.error && <p className="error-text add-source__error">{errorText(add.error)}</p>}
    </form>
  );
}

function SourceList() {
  const sources = useSources();
  if (!sources.data?.length) {
    return <p className="muted">Каналов пока нет. Добавьте публичный канал с афишей и нажмите «Обновить» в «Ближайших».</p>;
  }
  return (
    <div className="sources-table" role="table" aria-label="Каналы">
      {sources.data.map((source) => (
        <SourceRow key={source.id} source={source} />
      ))}
    </div>
  );
}

function SourceRow({ source }: { source: Source }) {
  const rename = useRenameSource();
  const remove = useDeleteSource();
  const [confirming, setConfirming] = useState(false);
  const state = source.last_error
    ? { label: source.last_error, kind: "error" }
    : source.last_refreshed_at
      ? { label: "Работает", kind: "ok" }
      : { label: "Ждёт обновления", kind: "new" };
  return (
    <div className="sources-table__row" role="row">
      <div className="sources-table__name" role="cell">
        <InlineEdit value={source.title} label="Название канала" className="sources-table__title" onSave={(title) => rename.mutate({ id: source.id, title })} />
        <a href={source.url} target="_blank" rel="noreferrer" className="sources-table__link">
          @{source.handle}
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
          <IconButton icon="trash" label="Удалить канал и его события" onClick={() => setConfirming(true)} />
        )}
      </span>
    </div>
  );
}
