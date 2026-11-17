import { useId, useState } from "react";

import type { InstagramReading, SitePreview } from "../api/client";
import { plural } from "../domain/dates";
import { Icon } from "../ui/Icon";

function instagramProfileUrl(handle: string): string {
  return `https://www.instagram.com/${handle}/`;
}

function storiesHint(highlights: number): string {
  if (highlights === 0) return "No highlights yet; new ones will be read";
  return `${highlights} ${plural(highlights, "highlight", "highlights")}; stories up to 30 days old, then every new one`;
}

export function InstagramPreviewCard({
  profile,
  adding,
  onAdd,
  onCancel,
}: {
  profile: SitePreview;
  adding: boolean;
  onAdd: (reading: InstagramReading) => void;
  onCancel: () => void;
}) {
  const titleId = useId();
  const [reading, setReading] = useState<InstagramReading>({ posts: true, stories: true });
  const nothing = !reading.posts && !reading.stories;
  return (
    <section className="site-preview" aria-labelledby={titleId}>
      <header className="site-preview__header">
        <span className="site-preview__icon" role="img" aria-label="Instagram profile">
          <Icon name="instagram" size={20} />
        </span>
        <div className="site-preview__name">
          <h3 id={titleId} className="site-preview__title">
            {profile.title}
          </h3>
          <a href={instagramProfileUrl(profile.handle)} target="_blank" rel="noreferrer" className="site-preview__link">
            @{profile.handle}
          </a>
        </div>
      </header>
      <fieldset className="instagram-reading">
        <legend className="label">What to read</legend>
        <ReadingOption name="Posts" hint="12 latest, then every new one" checked={reading.posts} onChange={(posts) => setReading({ ...reading, posts })} />
        <ReadingOption name="Pinned stories" hint={storiesHint(profile.highlights)} checked={reading.stories} onChange={(stories) => setReading({ ...reading, stories })} />
      </fieldset>
      <footer className="site-preview__actions">
        <button type="button" className="button button--quiet" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="button" onClick={() => onAdd(reading)} disabled={adding || nothing} title={nothing ? "Choose posts, pinned stories or both" : undefined}>
          {adding ? "Adding…" : "Add profile"}
        </button>
      </footer>
    </section>
  );
}

function ReadingOption({ name, hint, checked, onChange }: { name: string; hint: string; checked: boolean; onChange: (checked: boolean) => void }) {
  const nameId = useId();
  const hintId = useId();
  return (
    <label className="instagram-reading__option">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} aria-labelledby={nameId} aria-describedby={hintId} />
      <span className="instagram-reading__text">
        <span id={nameId} className="instagram-reading__name">
          {name}
        </span>
        <span id={hintId} className="instagram-reading__hint">
          {hint}
        </span>
      </span>
    </label>
  );
}
