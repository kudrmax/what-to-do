import type { Mention } from "../api/client";
import { ago } from "../domain/dates";
import { Icon } from "../ui/Icon";
import { Popover } from "../ui/Popover";
import "./OpenPostButton.css";

/** The organizer's own post goes first: it is the one to register through. */
function postsInOpeningOrder(mentions: Mention[]): Mention[] {
  return [...mentions].sort((a, b) => Number(b.data.from_organizer) - Number(a.data.from_organizer));
}

/** One button to the original post; with several sources, an arrow beside it picks another. */
export function OpenPostButton({ mentions }: { mentions: Mention[] }) {
  const [main, ...others] = postsInOpeningOrder(mentions);
  if (!main) return null;
  return (
    <div className="open-post">
      <a className={`button open-post__main${others.length ? " open-post__main--split" : ""}`} href={main.post_url} target="_blank" rel="noreferrer" data-tip={main.source_title}>
        <Icon name="external" size={16} />
        Открыть пост
      </a>
      {others.length > 0 && (
        <Popover
          className="open-post__more"
          trigger={(open, toggle) => (
            <button type="button" className="button open-post__toggle" aria-label="Выбрать источник" aria-expanded={open} onClick={toggle}>
              <Icon name="chevronDown" size={16} />
            </button>
          )}
        >
          {(close) => (
            <div className="open-post__menu" role="menu">
              {[main, ...others].map((mention) => (
                <a key={mention.id} className="popover__item open-post__item" role="menuitem" href={mention.post_url} target="_blank" rel="noreferrer" onClick={close}>
                  <span className="open-post__who">
                    <span className="open-post__name">{mention.source_title}</span>
                    <span className="open-post__when">{ago(mention.published_at)}</span>
                  </span>
                  {mention.data.from_organizer && <span className="badge badge--accent">организатор</span>}
                </a>
              ))}
            </div>
          )}
        </Popover>
      )}
    </div>
  );
}
