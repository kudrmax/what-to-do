import type { Tag, TagVisibility } from "../api/client";
import { Icon, type IconName } from "../ui/Icon";
import { Popover } from "../ui/Popover";

interface Choice {
  id: TagVisibility;
  icon: IconName;
  title: string;
  effect: string;
}

const CHOICES: Choice[] = [
  { id: "shown", icon: "eye", title: "Shown", effect: "Events with this tag stay in the feed" },
  { id: "hidden", icon: "eyeOff", title: "Hidden", effect: "An event leaves the feed when all its tags are hidden" },
  { id: "always_hidden", icon: "ban", title: "Always hidden", effect: "Every event with this tag leaves the feed, whatever its other tags" },
];

/** The eye of a tag row: opens the three ways a tag can keep events out of the feed. */
export function TagVisibilityMenu({ tag, onChange }: { tag: Tag; onChange: (visibility: TagVisibility) => void }) {
  const current = CHOICES.find((c) => c.id === tag.visibility) ?? CHOICES[0];
  return (
    <Popover
      className="tag-row__visibility"
      align="end"
      trigger={(open, toggle) => (
        <button
          type="button"
          className={`icon-button tag-visibility__trigger tag-visibility__trigger--${current.id}`}
          aria-label={`“${tag.name}”: ${current.title}. Change`}
          aria-haspopup="menu"
          aria-expanded={open}
          data-tip={open ? undefined : current.title}
          onClick={toggle}
        >
          <Icon name={current.icon} size={18} />
        </button>
      )}
    >
      {(close) => (
        <div className="tag-visibility" role="menu" aria-label={`Show events tagged “${tag.name}”`}>
          {CHOICES.map((choice) => (
            <button
              key={choice.id}
              type="button"
              role="menuitemradio"
              aria-checked={choice.id === current.id}
              className={`popover__item tag-visibility__item tag-visibility__item--${choice.id}`}
              onClick={() => {
                if (choice.id !== current.id) onChange(choice.id);
                close();
              }}
            >
              <Icon name={choice.icon} size={18} />
              <span className="tag-visibility__text">
                <span className="tag-visibility__title">{choice.title}</span>
                <span className="tag-visibility__effect">{choice.effect}</span>
              </span>
              <span className="tag-visibility__check">{choice.id === current.id && <Icon name="check" size={16} />}</span>
            </button>
          ))}
        </div>
      )}
    </Popover>
  );
}
