import { useState } from "react";

import type { Settings, Tag } from "../api/client";
import { useAddTag, useChangeSettings, useDefaultSettings, useHideTag, useRenameTag, useReorderTags, useSettings, useTags } from "../api/queries";
import { SECTIONS } from "../app/routes";
import { useThemeChoice, type ThemeChoice } from "../app/theme";
import { moved } from "../domain/tags";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { InlineEdit } from "../ui/InlineEdit";
import { Segmented, type SegmentedOption } from "../ui/Segmented";
import { UpdatesSection } from "../updates/UpdatesSection";
import { CollapsibleSection, Screen, Section, Subsection } from "../ui/Screen";
import { CitiesSection } from "./CitiesSection";
import { COLLECTIONS_ANCHOR, CollectionsSubsection } from "./CollectionsSettings";
import { PhonePageSection } from "./PhonePageSection";
import "./SettingsScreen.css";

export function SettingsScreen() {
  const settings = useSettings();
  return (
    <Screen title={SECTIONS.settings.title} narrow>
      <CitiesSection />
      <AppearanceSection />
      <Section title="Your feed" hint="What Claude looks for in posts and how it sorts events. Shared by all cities.">
        {settings.data && <PriorityWish wish={settings.data.priority_wish} />}
        <TagsSubsection />
      </Section>
      <PhonePageSection />
      <UpdatesSection />
      {settings.data && <AdvancedSection settings={settings.data} />}
    </Screen>
  );
}

const THEMES: SegmentedOption<ThemeChoice>[] = [
  { id: "system", label: "System" },
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
];

function AppearanceSection() {
  const [theme, setTheme] = useThemeChoice();
  return (
    <Section title="Appearance">
      <div className="setting-row">
        <div className="setting-row__text">
          <span className="setting-row__label">Theme</span>
          <p className="setting-row__hint">System switches between light and dark with your computer. The choice is kept in this browser.</p>
        </div>
        <div className="setting-row__control">
          <Segmented label="Theme" options={THEMES} value={theme} onChange={setTheme} />
        </div>
      </div>
    </Section>
  );
}

const WISH_EXAMPLE = "Above all I want events made for meeting people and talking. I am looking for friends";

function PriorityWish({ wish }: { wish: string }) {
  const change = useChangeSettings();
  const [draft, setDraft] = useState(wish);
  const save = (text: string) => change.mutate({ priority_wish: text }, { onSuccess: () => setDraft(text) });
  return (
    <Subsection
      title="What I look for first"
      hint="Describe it in your own words. Claude marks the events that fit with «For you»: they stand out in the feed, and the «For you» filter shows only them. After a change, the next refresh reads the recent posts again."
    >
      <div className="prompt">
        <textarea className="input wish__text" value={draft} rows={4} aria-label="What I look for first" placeholder={WISH_EXAMPLE} aria-invalid={change.isError} onChange={(e) => setDraft(e.target.value)} />
        <div className="prompt__actions">
          {change.error && <span className="error-text prompt__error">{errorText(change.error)}</span>}
          <button type="button" className="button button--quiet button--small" disabled={!wish || change.isPending} onClick={() => save("")}>
            Clear
          </button>
          <button type="button" className="button button--small" disabled={draft.trim() === wish || change.isPending} onClick={() => save(draft.trim())}>
            Save
          </button>
        </div>
      </div>
    </Subsection>
  );
}

function AdvancedSection({ settings }: { settings: Settings }) {
  return (
    <CollapsibleSection
      title="Advanced"
      hint="Safe to leave as they are. Change them only if cards come out wrong, or a refresh takes too long or uses too much of your Claude plan."
      openFor={COLLECTIONS_ANCHOR}
    >
      <CollectionsSubsection enabled={settings.collections_enabled} />
      <SettingRow
        name="recent_posts"
        value={settings.recent_posts}
        label="Recent posts per channel"
        hint="How many of each channel’s latest posts a refresh reads. More finds older events but makes every refresh longer. Takes effect from the next refresh."
      />
      <ModelsSubsection settings={settings} />
      <PromptsSubsection settings={settings} />
    </CollapsibleSection>
  );
}

type EditableSetting = "recent_posts";

type ModelSetting = "photo_model" | "extraction_model" | "matching_model";
type ClaudeModel = Settings[ModelSetting];

const MODELS: { id: ClaudeModel; name: string; tip: string }[] = [
  { id: "claude-haiku-5-5", name: "Haiku", tip: "Fastest and cheapest" },
  { id: "claude-sonnet-5-5", name: "Sonnet", tip: "More accurate than Haiku, costs more" },
  { id: "claude-opus-5-5", name: "Opus", tip: "Most capable and most expensive" },
];

function ModelsSubsection({ settings }: { settings: Settings }) {
  return (
    <Subsection title="Claude models" hint="Which model does each step. Bigger models are more accurate, slower and use more of your Claude plan. A new model takes effect from the next refresh.">
      <ModelRow name="photo_model" value={settings.photo_model} label="Photo reading" hint="Copies the text from posters and post images. Haiku mixes up tables and collages." />
      <ModelRow name="extraction_model" value={settings.extraction_model} label="Post and page reading" hint="Turns channel posts and website pages into events and venues." />
      <ModelRow name="matching_model" value={settings.matching_model} label="Duplicate merging" hint="Decides when two announcements are the same event." />
    </Subsection>
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
function SettingRow({ name, value, label, hint }: { name: EditableSetting; value: number; label: string; hint: string }) {
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
          type="number"
          defaultValue={value}
          aria-invalid={change.isError}
          onBlur={(e) => {
            const raw = e.target.value.trim();
            const next = Number(raw);
            if (raw !== "" && next !== value) change.mutate({ [name]: next });
          }}
        />
        {change.error && <span className="error-text">{errorText(change.error)}</span>}
      </div>
    </div>
  );
}

function TagsSubsection() {
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
    <Subsection
      title="Tags"
      hint={`Claude tags events only with these. Drag a tag to change the order on cards, click its name to rename it, click the eye to hide its events from the feed. An event leaves the feed only when all its tags are hidden; marked ones and ones that fit what you look for first stay. Events that fit no tag get “${fallback ?? "…"}”, which stays last.`}
    >
      <ul className="tag-list" aria-label="Tags">
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
        <input className="input tag-add__input" aria-label="New tag" value={name} onChange={(e) => setName(e.target.value)} placeholder="+ New tag" />
      </form>
      {(add.error || reorder.error) && <p className="error-text">{errorText(add.error ?? reorder.error)}</p>}
    </Subsection>
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
        <span className="tag-row__handle tag-row__handle--fixed" data-tip="Put when no other tag fits: always last" />
      ) : (
        <button
          type="button"
          className="tag-row__handle"
          aria-label={`Move “${tag.name}” with the up and down arrows`}
          data-tip="Drag to reorder"
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
        <InlineEdit value={tag.name} label={`New name for “${tag.name}”`} onSave={(name) => rename.mutate({ id: tag.id, name })} />
      </span>
      <IconButton
        icon={tag.hidden ? "eyeOff" : "eye"}
        label={tag.hidden ? "Blocked: events whose every tag is hidden leave the feed. Show them again" : "Hide events with this tag from the feed when all their tags are hidden"}
        aria-pressed={tag.hidden}
        className="tag-row__visibility"
        onClick={() => hide.mutate({ id: tag.id, hidden: !tag.hidden })}
      />
      {(rename.error || hide.error) && <span className="error-text tag-row__error">{errorText(rename.error ?? hide.error)}</span>}
    </li>
  );
}

function PromptsSubsection({ settings }: { settings: Settings }) {
  return (
    <Subsection title="Claude prompts" hint="The instructions Claude follows at each step. New text applies to posts that arrive after the next refresh; posts already read aren’t read again.">
      <PromptEditor name="extraction_prompt" value={settings.extraction_prompt} title="Post and page reading" hint="How to turn posts and website pages into events. Placeholders: {city} is the city, {language} the description language, {tags} the tag list, {fallback} the fallback tag." />
      <PromptEditor name="photo_prompt" value={settings.photo_prompt} title="Photo reading" hint="How to copy the text from posters and post images. Posts are then read together with this text." />
      <PromptEditor name="matching_prompt" value={settings.matching_prompt} title="Duplicate merging" hint="How to decide when two announcements are the same event." />
    </Subsection>
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
        <h4 className="prompt__title">{title}</h4>
        <p className="setting-row__hint">{hint}</p>
      </div>
      <textarea className="input prompt__text" value={draft} rows={12} spellCheck={false} aria-label={title} aria-invalid={change.isError} onChange={(e) => setDraft(e.target.value)} />
      <div className="prompt__actions">
        {change.error && <span className="error-text prompt__error">{errorText(change.error)}</span>}
        <button type="button" className="button button--quiet button--small" disabled={!initial || draft === initial} onClick={() => initial && save(initial)}>
          Restore default
        </button>
        <button type="button" className="button button--small" disabled={draft === value || !draft.trim() || change.isPending} onClick={() => save(draft)}>
          Save
        </button>
      </div>
    </div>
  );
}
