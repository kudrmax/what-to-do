import { useState } from "react";

import type { PotentialSource, PotentialSourceOrigin } from "../api/client";
import { useMarkPotentialSource, usePotentialSources } from "../api/queries";
import { ago, plural } from "../domain/dates";
import { Icon } from "../ui/Icon";
import { Section } from "../ui/Screen";
import "./PotentialSources.css";

const ORIGINS_SHOWN = 3;

const VIA = {
  forward: { icon: "forward", tip: "Пост переслан из этого канала" },
  link: { icon: "link", tip: "Пост ссылается на этот канал" },
} as const;

export function PotentialSources() {
  const found = usePotentialSources();
  const all = found.data ?? [];
  const waiting = all.filter((p) => !p.processed);
  const processed = all.filter((p) => p.processed);
  return (
    <div className="potential">
      <Section
        title="Потенциальные источники"
        hint="Каналы, из которых ваши источники пересылают посты или на которые ссылаются. Откройте канал и, если подходит, добавьте его выше. Отмеченные «Разобрано» больше не появятся."
      >
        {waiting.length ? (
          <ul className="potential__list">
            {waiting.map((p) => (
              <PotentialRow key={p.id} potential={p} />
            ))}
          </ul>
        ) : (
          <p className="muted">{processed.length ? "Всё разобрано." : "Пока ничего. Они находятся при обновлении, когда Claude читает посты."}</p>
        )}
        {processed.length > 0 && (
          <details className="potential__processed">
            <summary className="potential__summary">
              <span>Разобранные</span>
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
        <ul className="potential__origins" aria-label="Откуда">
          {origins.map((origin) => (
            <Origin key={origin.post_url} origin={origin} />
          ))}
        </ul>
        {hidden > 0 && (
          <button type="button" className="potential__more" onClick={() => setExpanded(true)}>
            Ещё {hidden} {plural(hidden, "пост", "поста", "постов")}
          </button>
        )}
      </div>
      <label className="potential__check">
        <input
          type="checkbox"
          checked={potential.processed}
          disabled={mark.isPending}
          onChange={(e) => mark.mutate({ id: potential.id, processed: e.target.checked })}
        />
        <span>Разобрано</span>
      </label>
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
