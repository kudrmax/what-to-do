import { useState, type ReactNode } from "react";

import type { CodexEffort, CodexModel, LlmProvider, Settings, Tag } from "../api/client";
import { useAddTag, useChangeSettings, useDefaultSettings, useChangeTag, useReorderTags, useTagVisibility, useRetag, useSettings, useTags } from "../api/queries";
import { SECTIONS } from "../app/routes";
import { useThemeChoice, type ThemeChoice } from "../app/theme";
import { plural } from "../domain/dates";
import { READERS, type Reader } from "../domain/readers";
import { moved } from "../domain/tags";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { TagVisibilityMenu } from "./TagVisibilityMenu";
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
  const reader = READERS[settings.data?.llm_provider ?? "claude"];
  return (
    <Screen title={SECTIONS.settings.title} narrow>
      <CitiesSection />
      <AppearanceSection />
      <Section title="Your feed" hint={`What ${reader.name} looks for in posts and how it sorts events. Shared by all cities.`}>
        {settings.data && <PriorityWish wish={settings.data.priority_wish} reader={reader} />}
        <TagsSubsection reader={reader} />
      </Section>
      <PhonePageSection />
      <UpdatesSection />
      {settings.data && <AdvancedSection settings={settings.data} reader={reader} />}
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

function PriorityWish({ wish, reader }: { wish: string; reader: Reader }) {
  const change = useChangeSettings();
  const [draft, setDraft] = useState(wish);
  const save = (text: string) => change.mutate({ priority_wish: text }, { onSuccess: () => setDraft(text) });
  return (
    <Subsection
      title="What I look for first"
      hint={`Describe it in your own words. ${reader.name} marks the events that fit with «For you»: they stand out in the feed, and the «For you» filter shows only them. After a change, the next refresh reads the recent posts again.`}
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

function AdvancedSection({ settings, reader }: { settings: Settings; reader: Reader }) {
  return (
    <CollapsibleSection
      title="Advanced"
      hint={`Safe to leave as they are. Change them only if cards come out wrong, or a refresh takes too long or uses too much of ${reader.plan}.`}
      openFor={COLLECTIONS_ANCHOR}
    >
      <CollectionsSubsection enabled={settings.collections_enabled} />
      <SettingRow
        name="recent_posts"
        value={settings.recent_posts}
        label="Recent posts per channel"
        hint="How many of each channel’s latest posts a refresh reads. More finds older events but makes every refresh longer. Takes effect from the next refresh."
      />
      <ProviderRow value={settings.llm_provider} />
      <ModelsSubsection settings={settings} reader={reader} />
      <PromptsSubsection settings={settings} reader={reader} />
    </CollapsibleSection>
  );
}

type EditableSetting = "recent_posts";

type ClaudeModelSetting = "photo_model" | "extraction_model" | "matching_model";
type ClaudeModel = Settings[ClaudeModelSetting];
type CodexStep = "photo" | "extraction" | "matching";

interface Choice<T> {
  id: T;
  name: string;
  tip: string;
}

const PROVIDERS: Choice<LlmProvider>[] = [
  { id: "claude", name: "Claude", tip: "Reads with your Claude plan through Claude Code" },
  { id: "codex", name: "Codex", tip: "Reads with your ChatGPT plan through Codex" },
];

const CLAUDE_MODELS: Choice<ClaudeModel>[] = [
  { id: "claude-haiku-5-5", name: "Haiku", tip: "Fastest and cheapest" },
  { id: "claude-sonnet-5-5", name: "Sonnet", tip: "More accurate than Haiku, costs more" },
  { id: "claude-opus-5-5", name: "Opus", tip: "Most capable and most expensive" },
];

const CODEX_MODELS: Choice<CodexModel>[] = [
  { id: "gpt-6-luna", name: "Luna", tip: "Fastest and lightest" },
  { id: "gpt-6.1-terra", name: "Terra", tip: "Fast" },
  { id: "gpt-6.2-sol", name: "Sol", tip: "Balanced" },
  { id: "gpt-6.2-astra", name: "Astra", tip: "Most capable and slowest" },
];

const CODEX_EFFORTS: Choice<CodexEffort>[] = [
  { id: "low", name: "Low", tip: "Answers quickest" },
  { id: "medium", name: "Medium", tip: "Thinks longer before answering" },
  { id: "high", name: "High", tip: "Thinks longest: slowest and uses the most of your plan" },
];

const STEPS: { claude: ClaudeModelSetting; codex: CodexStep; label: string; hint: string; claudeHint?: string }[] = [
  { claude: "photo_model", codex: "photo", label: "Photo reading", hint: "Copies the text from posters and post images.", claudeHint: "Haiku mixes up tables and collages." },
  { claude: "extraction_model", codex: "extraction", label: "Post and page reading", hint: "Turns channel posts and website pages into events and venues." },
  { claude: "matching_model", codex: "matching", label: "Duplicate merging", hint: "Decides when two announcements are the same event." },
];

function ModelsSubsection({ settings, reader }: { settings: Settings; reader: Reader }) {
  const codex = settings.llm_provider === "codex";
  return (
    <Subsection
      title={`${reader.name} models`}
      hint={`Which model does each step. Bigger models are more accurate, slower and use more of ${reader.plan}. A new model takes effect from the next refresh.`}
    >
      {STEPS.map((step) =>
        codex ? (
          <CodexModelRow
            key={step.codex}
            step={step.codex}
            model={settings[`codex_${step.codex}_model`]}
            effort={settings[`codex_${step.codex}_effort`]}
            label={step.label}
            hint={step.hint}
          />
        ) : (
          <ClaudeModelRow key={step.claude} name={step.claude} value={settings[step.claude]} label={step.label} hint={step.claudeHint ? `${step.hint} ${step.claudeHint}` : step.hint} />
        ),
      )}
    </Subsection>
  );
}

function ProviderRow({ value }: { value: LlmProvider }) {
  const change = useChangeSettings();
  return (
    <ChoiceRow label="Reads posts with" hint="Which subscription reads the posts. The other one keeps its models for when you switch back." error={change.error}>
      <Chips label="Reads posts with" choices={PROVIDERS} value={value} onPick={(llm_provider) => change.mutate({ llm_provider })} />
    </ChoiceRow>
  );
}

function ClaudeModelRow({ name, value, label, hint }: { name: ClaudeModelSetting; value: ClaudeModel; label: string; hint: string }) {
  const change = useChangeSettings();
  return (
    <ChoiceRow label={label} hint={hint} error={change.error}>
      <Chips label={label} choices={CLAUDE_MODELS} value={value} onPick={(model) => change.mutate({ [name]: model })} />
    </ChoiceRow>
  );
}

function CodexModelRow({ step, model, effort, label, hint }: { step: CodexStep; model: CodexModel; effort: CodexEffort; label: string; hint: string }) {
  const change = useChangeSettings();
  return (
    <ChoiceRow label={label} hint={hint} error={change.error}>
      <Chips label={label} choices={CODEX_MODELS} value={model} onPick={(next) => change.mutate({ [`codex_${step}_model`]: next })} dense />
      <span className="setting-row__caption">Thinking</span>
      <Chips label={`${label} thinking`} choices={CODEX_EFFORTS} value={effort} onPick={(next) => change.mutate({ [`codex_${step}_effort`]: next })} />
    </ChoiceRow>
  );
}

function ChoiceRow({ label, hint, error, children }: { label: string; hint: string; error: unknown; children: ReactNode }) {
  return (
    <div className="setting-row">
      <div className="setting-row__text">
        <span className="setting-row__label">{label}</span>
        <p className="setting-row__hint">{hint}</p>
      </div>
      <div className="setting-row__control">
        {children}
        {error != null && <span className="error-text">{errorText(error)}</span>}
      </div>
    </div>
  );
}

function Chips<T extends string>({ label, choices, value, onPick, dense = false }: { label: string; choices: Choice<T>[]; value: T; onPick: (id: T) => void; dense?: boolean }) {
  return (
    <div className={dense ? "settings-chips settings-chips--dense" : "settings-chips"} role="group" aria-label={label}>
      {choices.map((choice) => (
        <button key={choice.id} type="button" className="chip" aria-pressed={choice.id === value} data-tip={choice.tip} onClick={() => choice.id !== value && onPick(choice.id)}>
          {choice.name}
        </button>
      ))}
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

function TagsSubsection({ reader }: { reader: Reader }) {
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
      hint={`${reader.name} tags events only with these, up to four per event. Drag a tag to change the order on cards, click its name to rename it, and under the name tell ${reader.name} what the tag means. Click the eye to hide a tag. An event leaves the feed when all its tags are hidden, or when it has a tag that is always hidden; marked ones and ones that fit what you look for first stay. Events that fit no tag get “${fallback ?? "…"}”, which stays last.`}
    >
      <ul className="tag-list" aria-label="Tags">
        {list.map((tag, index) => (
          <TagRow
            key={tag.id}
            tag={tag}
            reader={reader}
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
      <Retag reader={reader} />
    </Subsection>
  );
}

interface TagRowProps {
  tag: Tag;
  reader: Reader;
  dragging: boolean;
  onDragStart: () => void;
  onDragEnter: () => void;
  onDragEnd: () => void;
  onMove: (step: -1 | 1) => void;
}

function TagRow({ tag, reader, dragging, onDragStart, onDragEnter, onDragEnd, onMove }: TagRowProps) {
  const change = useChangeTag();
  const visibility = useTagVisibility();
  const classes = ["tag-row", tag.visibility !== "shown" && "tag-row--hidden", dragging && "tag-row--dragging"].filter(Boolean).join(" ");
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
      <span className="tag-row__text">
        <span className="tag-row__name">
          <InlineEdit value={tag.name} label={`New name for “${tag.name}”`} onSave={(name) => change.mutate({ id: tag.id, change: { name } })} />
        </span>
        {!tag.is_fallback && (
          <span className="tag-row__meaning">
            <InlineEdit
              value={tag.description}
              label={`What “${tag.name}” means`}
              tip={`What this tag means for ${reader.name}`}
              placeholder="Add what it means"
              onSave={(description) => change.mutate({ id: tag.id, change: { description } })}
            />
          </span>
        )}
      </span>
      <TagVisibilityMenu tag={tag} onChange={(next) => visibility.mutate({ id: tag.id, visibility: next })} />
      {(change.error || visibility.error) && <span className="error-text tag-row__error">{errorText(change.error ?? visibility.error)}</span>}
    </li>
  );
}

/** Gives the upcoming events tags from the current list again, once the list or the meanings changed. */
function Retag({ reader }: { reader: Reader }) {
  const retag = useRetag();
  const status = retag.status;
  if (!status) return null;
  const finished = !retag.running && status.finished_at;
  const count = (n: number, one: string, other: string) => `${n} ${plural(n, one, other)}`;
  return (
    <div className="retag">
      <div className="retag__text">
        <span className="retag__title">Re-tag upcoming events</span>
        <span className="retag__hint">
          {retag.running
            ? `${reader.name} is reading ${count(status.cards_to_retag, "event", "events")} again.`
            : `${reader.name} reads ${count(status.upcoming, "upcoming event", "upcoming events")} again and tags them from this list, with the meanings: ${count(status.claude_calls, `${reader.name} call`, `${reader.name} calls`)}. Marks and plans stay.`}
        </span>
        {finished && status.errors.length === 0 && (
          <span className="retag__done" role="status">
            <Icon name="check" size={14} />
            {`${count(status.cards_retagged, "event", "events")} re-tagged, ${status.cards_changed} with new tags`}
          </span>
        )}
        {finished &&
          status.errors.map((error) => (
            <span key={error} className="error-text">
              {error}
            </span>
          ))}
        {retag.error && <span className="error-text">{errorText(retag.error)}</span>}
      </div>
      <button type="button" className="button button--small retag__button" onClick={retag.start} disabled={retag.running || status.upcoming === 0} aria-busy={retag.running}>
        {retag.running && <Icon name="refresh" size={14} strokeWidth={2.2} className="retag__spin" />}
        {retag.running ? `${status.cards_retagged} of ${status.cards_to_retag}` : "Re-tag"}
      </button>
    </div>
  );
}

function PromptsSubsection({ settings, reader }: { settings: Settings; reader: Reader }) {
  return (
    <Subsection
      title={`${reader.name} prompts`}
      hint={`The instructions ${reader.name} follows at each step. New text applies to posts that arrive after the next refresh; posts already read aren’t read again.`}
    >
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
