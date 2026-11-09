import { useState, type FormEvent } from "react";

import { ApiError, type Settings, type Source, type Tag } from "../api/client";
import { useAddCity, useAddSource, useAddTag, useChangeSettings, useCities, useDeleteSource, useRenameSource, useRenameTag, useSettings, useSources, useTags } from "../api/hooks";
import { Icon } from "../components/Icon";
import { Screen } from "../components/Screen";
import { ago } from "../domain/dates";
import "./SourcesScreen.css";

export function SourcesScreen() {
  const cities = useCities();
  const hasCity = cities.data?.some((city) => city.active) ?? false;
  return (
    <Screen title="Источники" narrow>
      <CitiesSection />
      {hasCity && (
        <>
          <AddSourceForm />
          <SourceList />
        </>
      )}
      <TagsSection />
      <ReadingSection />
    </Screen>
  );
}

function errorText(error: unknown): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : "Не получилось, попробуйте ещё раз";
}

function CitiesSection() {
  const cities = useCities();
  const changeSettings = useChangeSettings();
  const [adding, setAdding] = useState(cities.data?.length === 0);
  const showForm = adding || cities.data?.length === 0;
  return (
    <section className="section">
      <h2 className="section__label">Активный город</h2>
      <div className="city-chips">
        {cities.data?.map((city) => (
          <button key={city.id} type="button" className="city-chip" aria-pressed={city.active} onClick={() => !city.active && changeSettings.mutate({ active_city_id: city.id })}>
            {city.name}
          </button>
        ))}
        {!showForm && (
          <button type="button" className="city-chip city-chip--add" aria-label="Добавить город" onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
          </button>
        )}
      </div>
      {showForm && <AddCityForm onDone={() => setAdding(false)} canCancel={(cities.data?.length ?? 0) > 0} />}
    </section>
  );
}

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];

function AddCityForm({ onDone, canCancel }: { onDone: () => void; canCancel: boolean }) {
  const addCity = useAddCity();
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    addCity.mutate({ name: name.trim(), timezone }, { onSuccess: onDone });
  };
  return (
    <form className="form" onSubmit={submit}>
      <div className="field field--wide">
        <label htmlFor="city-name">Город</label>
        <input id="city-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например, Белград" autoFocus required />
      </div>
      <div className="field">
        <label htmlFor="city-zone">Часовой пояс</label>
        <input id="city-zone" value={timezone} onChange={(e) => setTimezone(e.target.value)} list="zones" required />
        <datalist id="zones">
          {ZONES.map((zone) => (
            <option key={zone} value={zone} />
          ))}
        </datalist>
      </div>
      <div className="form__buttons">
        {canCancel && (
          <button type="button" className="button button--quiet" onClick={onDone}>
            Отмена
          </button>
        )}
        <button type="submit" className="button" disabled={addCity.isPending || !name.trim()}>
          Добавить
        </button>
      </div>
      {addCity.error && <p className="form__error">{errorText(addCity.error)}</p>}
    </form>
  );
}

function AddSourceForm() {
  const addSource = useAddSource();
  const [link, setLink] = useState("");
  const [title, setTitle] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    addSource.mutate(
      { link: link.trim(), title: title.trim() },
      {
        onSuccess: () => {
          setLink("");
          setTitle("");
        },
      },
    );
  };
  return (
    <form className="form form--panel" onSubmit={submit}>
      <div className="field field--wide">
        <label htmlFor="src-url">Ссылка</label>
        <input id="src-url" value={link} onChange={(e) => setLink(e.target.value)} placeholder="t.me/канал" required />
      </div>
      <div className="field">
        <label htmlFor="src-name">Название</label>
        <input id="src-name" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Как в Telegram" />
      </div>
      <div className="form__buttons">
        <button type="submit" className="button" disabled={addSource.isPending || !link.trim()}>
          {addSource.isPending ? "Проверяю…" : "Добавить"}
        </button>
      </div>
      {addSource.error && <p className="form__error">{errorText(addSource.error)}</p>}
    </form>
  );
}

function SourceList() {
  const sources = useSources();
  if (!sources.data?.length) {
    return <p className="hint">Источников пока нет. Добавьте публичный Telegram-канал с афишей, потом нажмите «Обновить» в ленте.</p>;
  }
  return (
    <div className="source-rows">
      {sources.data.map((source) => (
        <SourceRow key={source.id} source={source} />
      ))}
    </div>
  );
}

function SourceRow({ source }: { source: Source }) {
  const rename = useRenameSource();
  const remove = useDeleteSource();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(source.title);
  const [confirming, setConfirming] = useState(false);
  const state = source.last_error
    ? { label: source.last_error, kind: "error" }
    : source.last_refreshed_at
      ? { label: "Работает", kind: "ok" }
      : { label: "Ещё не обновлялся", kind: "new" };

  return (
    <div className="source-row">
      <div className="source-row__name">
        {editing ? (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              rename.mutate({ id: source.id, title: title.trim() }, { onSuccess: () => setEditing(false) });
            }}
          >
            <input aria-label="Название источника" value={title} onChange={(e) => setTitle(e.target.value)} onFocus={(e) => e.target.select()} onBlur={() => setEditing(false)} autoFocus />
          </form>
        ) : (
          <button type="button" className="source-row__title" title="Переименовать" onClick={() => setEditing(true)}>
            {source.title}
          </button>
        )}
        <a href={source.url} target="_blank" rel="noreferrer" className="source-row__kind">
          Telegram
        </a>
      </div>
      <div className="source-row__stat">
        <span>Обновлено</span>
        <strong>{source.last_refreshed_at ? ago(source.last_refreshed_at) : "—"}</strong>
      </div>
      <div className="source-row__stat">
        <span>Событий</span>
        <strong>{source.events_found}</strong>
      </div>
      <span className={`state state--${state.kind}`}>{state.label}</span>
      {confirming ? (
        <div className="source-row__confirm">
          <button type="button" className="button button--danger" onClick={() => remove.mutate(source.id)}>
            Удалить
          </button>
          <button type="button" className="button button--quiet" onClick={() => setConfirming(false)}>
            Нет
          </button>
        </div>
      ) : (
        <button type="button" className="icon-button" aria-label={`Удалить «${source.title}»`} title="Удалить источник" onClick={() => setConfirming(true)}>
          <Icon name="trash" size={16} />
        </button>
      )}
    </div>
  );
}

function TagsSection() {
  const tags = useTags();
  const addTag = useAddTag();
  const [name, setName] = useState("");
  return (
    <section className="section">
      <h2 className="section__label">Теги</h2>
      <p className="hint">Claude ставит событиям только эти теги. Если ни один не подходит — «не распознано»: по таким событиям видно, какого тега не хватает.</p>
      <div className="tag-list">
        {tags.data?.map((tag) => (
          <TagChip key={tag.id} tag={tag} />
        ))}
        <form
          className="tag-add"
          onSubmit={(e) => {
            e.preventDefault();
            addTag.mutate(name.trim(), { onSuccess: () => setName("") });
          }}
        >
          <input aria-label="Новый тег" value={name} onChange={(e) => setName(e.target.value)} placeholder="Новый тег" />
          {name.trim() && (
            <button type="submit" className="icon-button" aria-label="Добавить тег">
              <Icon name="plus" size={16} />
            </button>
          )}
        </form>
      </div>
      {addTag.error && <p className="form__error">{errorText(addTag.error)}</p>}
    </section>
  );
}

function TagChip({ tag }: { tag: Tag }) {
  const rename = useRenameTag();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(tag.name);
  if (tag.is_fallback) {
    return <span className="tag tag--fallback">{tag.name}</span>;
  }
  if (editing) {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          rename.mutate({ id: tag.id, name: name.trim() }, { onSuccess: () => setEditing(false) });
        }}
      >
        <input className="tag tag--editing" aria-label={`Новое имя тега «${tag.name}»`} value={name} onChange={(e) => setName(e.target.value)} onFocus={(e) => e.target.select()} onBlur={() => setEditing(false)} autoFocus />
      </form>
    );
  }
  return (
    <button type="button" className="tag" title="Переименовать" onClick={() => setEditing(true)}>
      {tag.name}
    </button>
  );
}

function ReadingSection() {
  const settings = useSettings();
  if (!settings.data) return null;
  return (
    <section className="section">
      <h2 className="section__label">Чтение постов</h2>
      <div className="settings-grid">
        <SettingField name="recent_posts" label="Читать последних постов канала" type="number" value={settings.data.recent_posts} />
        <SettingField name="description_language" label="Язык описаний" type="text" value={settings.data.description_language} />
      </div>
    </section>
  );
}

type EditableSetting = Exclude<keyof Settings, "active_city_id">;

/** Saves on leaving the field; limits are the backend's, so its message is shown as is. */
function SettingField({ name, label, type, value }: { name: EditableSetting; label: string; type: "number" | "text"; value: string | number }) {
  const change = useChangeSettings();
  const id = `setting-${name}`;
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <div className="settings-grid__field">
        <input
          id={id}
          type={type}
          defaultValue={value}
          aria-invalid={change.isError}
          onBlur={(e) => {
            const raw = e.target.value.trim();
            const next = type === "number" ? Number(raw) : raw;
            if (raw !== "" && next !== value) change.mutate({ [name]: next });
          }}
        />
        {change.error && <span className="form__error">{errorText(change.error)}</span>}
      </div>
    </>
  );
}
