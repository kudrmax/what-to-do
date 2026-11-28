import { useState } from "react";

import type { PotentialSource, PotentialSourceOrigin } from "../api/client";
import { useAdoptPotentialSource, useMarkPotentialSource, usePotentialSources } from "../api/queries";
import { useReader } from "../api/useReader";
import { ago, plural } from "../domain/dates";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { Section } from "../ui/Screen";
import "./PotentialSources.css";

const ORIGINS_SHOWN = 3;

const VIA = {
  forward: { icon: "forward", tip: "Post forwarded from this channel" },
  link: { icon: "link", tip: "A post or website page links to this channel" },
} as const;

export function PotentialSources() {
  const found = usePotentialSources();
  const reader = useReader();
  const all = found.data ?? [];
  const waiting = all.filter((p) => !p.processed);
  const processed = all.filter((p) => p.processed);
  return (
    <div className="potential">
      <Section
        title="Potential sources"
        hint="Channels your sources forward posts from or link to. Open a channel and decide whether to add it to your sources or dismiss it as not interesting. Dismissed channels won’t appear again."
      >
        {waiting.length ? (
          <ul className="potential__list">
            {waiting.map((p) => (
              <PotentialRow key={p.id} potential={p} />
            ))}
          </ul>
        ) : (
          <p className="muted">{processed.length ? "No new channels." : `Nothing yet. They turn up during a refresh, when ${reader.name} reads posts.`}</p>
        )}
        {processed.length > 0 && (
          <details className="potential__processed">
            <summary className="potential__summary">
              <span>Dismissed</span>
              <span className="potential__count">{processed.length}</span>
            </summary>
            <ul className="potential__list">
              {processed.map((p) => (
                <PotentialRow key={p.id} potential={p} />
              ))}
            </ul>
          </details>
        )}
      </Section>
    </div>
  );
}

function PotentialRow({ potential }: { potential: PotentialSource }) {
  const mark = useMarkPotentialSource();
  const adopt = useAdoptPotentialSource();
  const busy = mark.isPending || adopt.isPending;
  const [expanded, setExpanded] = useState(false);
  const origins = expanded ? potential.origins : potential.origins.slice(0, ORIGINS_SHOWN);
  const hidden = potential.origins.length - origins.length;
  return (
    <li className="potential__row">
      <div className="potential__main">
        <a href={potential.url} target="_blank" rel="noreferrer" className="potential__handle">
          <span>@{potential.handle}</span>
          <Icon name="external" size={14} />
        </a>
        <ul className="potential__origins" aria-label="Found in">
          {origins.map((origin) => (
            <Origin key={origin.post_url} origin={origin} />
          ))}
        </ul>
        {hidden > 0 && (
          <button type="button" className="potential__more" onClick={() => setExpanded(true)}>
            {hidden} more {plural(hidden, "post", "posts")}
          </button>
        )}
        {adopt.error && <p className="error-text">Couldn’t add: {errorText(adopt.error)}</p>}
      </div>
      <div className="potential__actions">
        {potential.processed ? (
          <button type="button" className="button button--small button--quiet" disabled={busy} onClick={() => mark.mutate({ id: potential.id, processed: false })}>
            Restore
          </button>
        ) : (
          <>
            <button type="button" className="button button--small" disabled={busy} onClick={() => adopt.mutate(potential.id)}>
              {adopt.isPending ? "Adding…" : "Add to sources"}
            </button>
            <button type="button" className="button button--small button--quiet" disabled={busy} onClick={() => mark.mutate({ id: potential.id, processed: true })}>
              Not interesting
            </button>
          </>
        )}
      </div>
    </li>
  );
}

function Origin({ origin }: { origin: PotentialSourceOrigin }) {
  const via = VIA[origin.via];
  return (
    <li className="potential__origin">
      <span className="potential__via" data-tip={via.tip} aria-label={via.tip} tabIndex={0}>
        <Icon name={via.icon} size={14} />
      </span>
      <a href={origin.post_url} target="_blank" rel="noreferrer" className="potential__post">
        {origin.source_title}
      </a>
      <span className="potential__when">{ago(origin.published_at)}</span>
    </li>
  );
}
