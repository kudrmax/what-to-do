import { useState, type FormEvent } from "react";

import type { Settings, Tag } from "../api/client";
import { useAddCity, useAddTag, useChangeSettings, useCities, useDefaultSettings, useHideTag, useRenameTag, useReorderTags, useSettings, useTags } from "../api/queries";
import { SECTIONS } from "../app/routes";
import { moved } from "../domain/tags";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { InlineEdit } from "../ui/InlineEdit";
import { UpdatesSection } from "../updates/UpdatesSection";
import { Screen, Section } from "../ui/Screen";
import "./SettingsScreen.css";

export function SettingsScreen() {
  const settings = useSettings();
  return (
    <Screen title={SECTIONS.settings.title} narrow>
      <CitiesSection />
      {settings.data && <ReadingSection settings={settings.data} />}
      {settings.data && <ModelsSection settings={settings.data} />}
      <TagsSection />
      {settings.data && <PromptsSection settings={settings.data} />}
      <UpdatesSection />
    </Screen>
  );
}

function CitiesSection() {
  const cities = useCities();
  const settings = useSettings();
  const change = useChangeSettings();
  const [adding, setAdding] = useState(false);
  const empty = cities.data?.length === 0;
  return (
    <Section title="Город" hint="Лента, календарь и каналы показываются для выбранного города. Каналы другого города не пропадают — переключитесь обратно, и они вернутся.">
      <div className="settings-chips">
        {cities.data?.map((city) => (
          <button key={city.id} type="button" className="chip" aria-pressed={city.id === settings.data?.active_city_id} onClick={() => change.mutate({ active_city_id: city.id })}>
            {city.name}
          </button>
        ))}
        {!adding && !empty && (
          <button type="button" className="chip chip--dashed" onClick={() => setAdding(true)}>
            + Добавить город
          </button>
        )}
      </div>
      {(adding || empty) && <AddCityForm onDone={() => setAdding(false)} canCancel={!empty} />}
    </Section>
  );
}

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];

function AddCityForm({ onDone, canCancel }: { onDone: () => void; canCancel: boolean }) {
  const add = useAddCity();
  const [name, setName] = useState("");
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  const submit = (event: FormEvent) => {
    event.preventDefault();
    add.mutate({ name: name.trim(), timezone }, { onSuccess: onDone });
  };
  return (
    <form className="settings-form" onSubmit={submit}>
      <label className="settings-form__field settings-form__field--wide">
        <span className="label">Город</span>
        <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Например, Белград" autoFocus required />
      </label>
      <label className="settings-form__field">
        <span className="label">Часовой пояс</span>
        <input className="input" value={timezone} onChange={(e) => setTimezone(e.target.value)} list="zones" required />
        <datalist id="zones">
          {ZONES.map((zone) => (
            <option key={zone} value={zone} />
          ))}
        </datalist>
      </label>
      {canCancel && (
        <button type="button" className="button button--quiet" onClick={onDone}>
          Отмена
        </button>
      )}
      <button type="submit" className="button" disabled={add.isPending || !name.trim()}>
        Добавить
      </button>
      {add.error && <p className="error-text settings-form__error">{errorText(add.error)}</p>}
    </form>
  );
}

function ReadingSection({ settings }: { settings: Settings }) {
  return (
    <Section title="Чтение постов">
      <SettingRow name="recent_posts" type="number" value={settings.recent_posts} label="Последних постов канала" hint="Столько свежих постов каждого канала читается. Если увеличить, при следующем обновлении дочитаются более старые." />
      <SettingRow name="description_language" type="text" value={settings.description_language} label="Язык описаний" hint="На этом языке Claude пишет названия и описания событий." />
    </Section>
  );
}

type EditableSetting = "recent_posts" | "description_language";

type ModelSetting = "photo_model" | "extraction_model" | "matching_model";
type ClaudeModel = Settings[ModelSetting];

const MODELS: { id: ClaudeModel; name: string; tip: string }[] = [
  { id: "claude-haiku-5-5", name: "Haiku", tip: "Быстрее и дешевле всех" },
  { id: "claude-sonnet-5-5", name: "Sonnet", tip: "Точнее Haiku, дороже" },
  { id: "claude-opus-5-5", name: "Opus", tip: "Самая сильная и самая дорогая" },
];

function ModelsSection({ settings }: { settings: Settings }) {
  return (
    <Section title="Модели Claude" hint="Новая модель действует со следующего обновления.">
      <ModelRow name="photo_model" value={settings.photo_model} label="Расшифровка фото" hint="Переписывает текст с афиш и картинок постов. Haiku путает таблицы и коллажи." />
      <ModelRow name="extraction_model" value={settings.extraction_model} label="Разбор постов" hint="Превращает посты в события и места." />
      <ModelRow name="matching_model" value={settings.matching_model} label="Склейка повторов" hint="Решает, что два анонса — одно событие." />
    </Section>
  );
}

function ModelRow({ name, value, label, hint }: { name: ModelSetting; value: ClaudeModel; label: string; hint: string }) {
  const change = useChangeSettings();
  return (
    <div className="setting-row">
      <div className="setting-row__text">
        <span className="setting-row__label">{label}</span>
        <p className="setting-row__hint">{hint}</p>
      </div>
      <div className="setting-row__control">
        <div className="settings-chips" role="group" aria-label={label}>
          {MODELS.map((model) => (
            <button key={model.id} type="button" className="chip" aria-pressed={model.id === value} data-tip={model.tip} onClick={() => model.id !== value && change.mutate({ [name]: model.id })}>
              {model.name}
            </button>
          ))}
        </div>
        {change.error && <span className="error-text">{errorText(change.error)}</span>}
      </div>
    </div>
  );
}

/** One setting: its name and what it does on the left, the field on the right; saves on leaving the field. */
function SettingRow({ name, type, value, label, hint }: { name: EditableSetting; type: "number" | "text"; value: string | number; label: string; hint: string }) {
  const change = useChangeSettings();
  const id = `setting-${name}`;
  return (
    <div className="setting-row">
      <div className="setting-row__text">
        <label htmlFor={id} className="setting-row__label">
          {label}
        </label>
        <p className="setting-row__hint">{hint}</p>
      </div>
      <div className="setting-row__control">
        <input
          id={id}
          className="input"
          type={type}
          defaultValue={value}
          aria-invalid={change.isError}
          onBlur={(e) => {
            const raw = e.target.value.trim();
            const next = type === "number" ? Number(raw) : raw;
            if (raw !== "" && next !== value) change.mutate({ [name]: next });
          }}
        />
        {change.error && <span className="error-text">{errorText(change.error)}</span>}
      </div>
    </div>
  );
}

function TagsSection() {
  const tags = useTags();
  const add = useAddTag();
  const reorder = useReorderTags();
  const [name, setName] = useState("");
  const [dragged, setDragged] = useState<number | null>(null);
  const list = tags.data ?? [];
  const fallback = list.find((t) => t.is_fallback)?.name;
  const movable = list.filter((t) => !t.is_fallback).length;
  const move = (from: number, to: number) => {
    if (from !== to && to >= 0 && to < movable) reorder.mutate(moved(list, from, to));
  };
  return (
    <Section
      title="Теги"
      hint={`Claude ставит событиям только эти теги. Если ни один не подходит — «${fallback ?? "…"}»: по таким событиям видно, какого тега не хватает. Перетащите тег, чтобы поменять порядок: в нём теги показываются на карточках. Тег со скрытым глазом — в чёрном списке: такие события не попадают в ленту, но размеченные остаются в «Собираюсь пойти».`}
    >
      <ul className="tag-list" aria-label="Теги">
        {list.map((tag, index) => (
          <TagRow
            key={tag.id}
            tag={tag}
            dragging={dragged === index}
            onDragStart={() => setDragged(index)}
            onDragEnter={() => {
              if (dragged === null || tag.is_fallback || dragged === index) return;
              move(dragged, index);
              setDragged(index);
            }}
            onDragEnd={() => setDragged(null)}
            onMove={(step) => move(index, index + step)}
          />
        ))}
      </ul>
      <form
        className="tag-add"
        onSubmit={(e) => {
          e.preventDefault();
          add.mutate(name.trim(), { onSuccess: () => setName("") });
        }}
      >
        <input className="input tag-add__input" aria-label="Новый тег" value={name} onChange={(e) => setName(e.target.value)} placeholder="+ Новый тег" />
      </form>
      {(add.error || reorder.error) && <p className="error-text">{errorText(add.error ?? reorder.error)}</p>}
    </Section>
  );
}

interface TagRowProps {
  tag: Tag;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnter: () => void;
  onDragEnd: () => void;
  onMove: (step: -1 | 1) => void;
}

function TagRow({ tag, dragging, onDragStart, onDragEnter, onDragEnd, onMove }: TagRowProps) {
  const rename = useRenameTag();
  const hide = useHideTag();
  const classes = ["tag-row", tag.hidden && "tag-row--hidden", dragging && "tag-row--dragging"].filter(Boolean).join(" ");
  return (
    <li
      className={classes}
      draggable={!tag.is_fallback}
      onDragStart={(e) => {
        e.dataTransfer.effectAllowed = "move";
        e.dataTransfer.setData("text/plain", tag.name);
        onDragStart();
      }}
      onDragEnter={onDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragEnd={onDragEnd}
      onDrop={(e) => e.preventDefault()}
    >
      {tag.is_fallback ? (
        <span className="tag-row__handle tag-row__handle--fixed" data-tip="Этот тег всегда последний" />
      ) : (
        <button
          type="button"
          className="tag-row__handle"
          aria-label={`Переставить «${tag.name}»: стрелки вверх и вниз`}
          data-tip="Перетащите, чтобы поменять порядок"
          onKeyDown={(e) => {
            if (e.key === "ArrowUp" || e.key === "ArrowDown") {
              e.preventDefault();
              onMove(e.key === "ArrowUp" ? -1 : 1);
            }
          }}
        >
          <Icon name="grip" size={16} />
        </button>
      )}
      <span className="tag-row__name">
        {tag.is_fallback ? (
          <span data-tip="Этот тег не переименовывается">{tag.name}</span>
        ) : (
          <InlineEdit value={tag.name} label={`Новое имя тега «${tag.name}»`} onSave={(name) => rename.mutate({ id: tag.id, name })} />
        )}
      </span>
      <IconButton
        icon={tag.hidden ? "eyeOff" : "eye"}
        label={tag.hidden ? "В чёрном списке: события с тегом скрыты из ленты. Вернуть в ленту" : "Скрывать события с этим тегом из ленты"}
        aria-pressed={tag.hidden}
        className="tag-row__visibility"
        onClick={() => hide.mutate({ id: tag.id, hidden: !tag.hidden })}
      />
      {(rename.error || hide.error) && <span className="error-text tag-row__error">{errorText(rename.error ?? hide.error)}</span>}
    </li>
  );
}

function PromptsSection({ settings }: { settings: Settings }) {
  return (
    <Section title="Промпты для Claude" hint="Новый текст действует для постов, которые придут после следующего обновления. Уже разобранные посты заново не читаются.">
      <PromptEditor name="extraction_prompt" value={settings.extraction_prompt} title="Разбор постов" hint="Как превращать посты в события. Подстановки: {city} — город, {language} — язык описаний, {tags} — список тегов, {fallback} — тег «не распознано»." />
      <PromptEditor name="photo_prompt" value={settings.photo_prompt} title="Расшифровка фото" hint="Как переписывать текст с афиш и картинок постов. Посты потом читаются вместе с этим текстом." />
      <PromptEditor name="matching_prompt" value={settings.matching_prompt} title="Склейка повторов" hint="Как решать, что два анонса — одно и то же событие." />
    </Section>
  );
}

function PromptEditor({ name, value, title, hint }: { name: "extraction_prompt" | "photo_prompt" | "matching_prompt"; value: string; title: string; hint: string }) {
  const defaults = useDefaultSettings();
  const change = useChangeSettings();
  const [draft, setDraft] = useState(value);
  const initial = defaults.data?.[name];
  const save = (text: string) => change.mutate({ [name]: text }, { onSuccess: () => setDraft(text) });
  return (
    <div className="prompt">
      <div className="prompt__head">
        <h3 className="prompt__title">{title}</h3>
        <p className="setting-row__hint">{hint}</p>
      </div>
      <textarea className="input prompt__text" value={draft} rows={12} spellCheck={false} aria-label={title} aria-invalid={change.isError} onChange={(e) => setDraft(e.target.value)} />
      <div className="prompt__actions">
        {change.error && <span className="error-text prompt__error">{errorText(change.error)}</span>}
        <button type="button" className="button button--quiet button--small" disabled={!initial || draft === initial} onClick={() => initial && save(initial)}>
          Вернуть как было
        </button>
        <button type="button" className="button button--small" disabled={draft === value || !draft.trim() || change.isPending} onClick={() => save(draft)}>
          Сохранить
        </button>
      </div>
    </div>
  );
}
