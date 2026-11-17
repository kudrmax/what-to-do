import { NavLink } from "react-router-dom";

import type { EventCard } from "../api/client";
import { useCollections, useSetCollections } from "../api/queries";
import { useReadOnly } from "../app/readOnly";
import { SECTIONS } from "../app/routes";
import { Icon } from "../ui/Icon";
import { Popover } from "../ui/Popover";
import { useCollectionsOn } from "./useCollectionsOn";
import "./CollectionButton.css";

/** A heart that puts the event into the user's collections; filled while it is in any of them. */
export function CollectionButton({ event, place }: { event: EventCard; place: "card" | "window" }) {
  const readOnly = useReadOnly();
  const on = useCollectionsOn();
  const collections = useCollections(on).data ?? [];
  const change = useSetCollections();
  if (readOnly || !on) return null;
  const chosen = new Set(event.collection_ids);
  const collected = chosen.size > 0;
  const toggle = (id: number) => {
    const next = new Set(chosen);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    change.mutate({ id: event.id, collectionIds: [...next] });
  };
  const label = collected ? "In collections" : "Add to a collection";
  return (
    <Popover
      className={`collect collect--${place}`}
      align="end"
      trigger={(open, toggleMenu) => (
        <button
          type="button"
          className={`collect__button${collected ? " collect__button--on" : ""}`}
          aria-label={label}
          data-tip={open ? undefined : label}
          data-tip-below={place === "window" ? undefined : ""}
          aria-haspopup="menu"
          aria-expanded={open}
          onClick={toggleMenu}
        >
          <Icon name="heart" size={place === "window" ? 20 : 17} filled={collected} />
        </button>
      )}
    >
      {() => (
        <div role="menu" aria-label="Collections">
          {collections.map((collection) => (
            <button
              key={collection.id}
              type="button"
              role="menuitemcheckbox"
              aria-checked={chosen.has(collection.id)}
              className="popover__item collect__option"
              onClick={() => toggle(collection.id)}
            >
              <span className="collect__name">{collection.name}</span>
              {chosen.has(collection.id) && <Icon name="check" size={16} className="collect__check" />}
            </button>
          ))}
          <div className="popover__footer">
            <NavLink to={`${SECTIONS.settings.path}#collections`} className="popover__item">
              <Icon name="settings" size={16} />
              Manage collections
            </NavLink>
          </div>
        </div>
      )}
    </Popover>
  );
}
