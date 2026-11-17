import { useState } from "react";

import type { Collection } from "../api/client";
import { useAddCollection, useChangeSettings, useCollections, useDeleteCollection, useRenameCollection } from "../api/queries";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { InlineEdit } from "../ui/InlineEdit";
import { Segmented } from "../ui/Segmented";
import { Subsection } from "../ui/Screen";
import "./CollectionsSettings.css";

export const COLLECTIONS_ANCHOR = "collections";

/** The switch for collections and, while it is on, the collections themselves. */
export function CollectionsSubsection({ enabled }: { enabled: boolean }) {
  const change = useChangeSettings();
  return (
    <div id={COLLECTIONS_ANCHOR}>
      <Subsection
        title="Collections"
        hint="Your own sets of events to keep, for example the funniest or the most unusual ones. A heart on every card adds the event to them, and Collections in the menu shows each set as a feed. Turning them off only hides them."
      >
        <div className="setting-row">
          <div className="setting-row__text">
            <span className="setting-row__label">Show collections</span>
          </div>
          <div className="setting-row__control">
            <Segmented
              label="Show collections"
              options={[
                { id: "off", label: "Off" },
                { id: "on", label: "On" },
              ]}
              value={enabled ? "on" : "off"}
              onChange={(id) => change.mutate({ collections_enabled: id === "on" })}
            />
            {change.error && <span className="error-text">{errorText(change.error)}</span>}
          </div>
        </div>
        {enabled && <CollectionList />}
      </Subsection>
    </div>
  );
}

function CollectionList() {
  const collections = useCollections();
  const add = useAddCollection();
  const [name, setName] = useState("");
  const list = collections.data ?? [];
  return (
    <>
      {list.length > 0 && (
        <ul className="tag-list" aria-label="Collections">
          {list.map((collection) => (
            <CollectionRow key={collection.id} collection={collection} />
          ))}
        </ul>
      )}
      <form
        className="tag-add"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) add.mutate(name.trim(), { onSuccess: () => setName("") });
        }}
      >
        <input className="input tag-add__input collection-add__input" aria-label="New collection" value={name} onChange={(e) => setName(e.target.value)} placeholder="+ New collection" />
      </form>
      {add.error && <p className="error-text">{errorText(add.error)}</p>}
    </>
  );
}

function CollectionRow({ collection }: { collection: Collection }) {
  const rename = useRenameCollection();
  const remove = useDeleteCollection();
  const [confirming, setConfirming] = useState(false);
  const drop = () => (collection.size > 0 ? setConfirming(true) : remove.mutate(collection.id));
  return (
    <li className="tag-row collection-row">
      <Icon name="heart" size={16} className="collection-row__icon" />
      <span className="tag-row__name">
        <InlineEdit value={collection.name} label={`New name for “${collection.name}”`} onSave={(name) => rename.mutate({ id: collection.id, name })} />
      </span>
      {confirming ? (
        <span className="collection-row__confirm">
          <span className="collection-row__question">
            Delete it? Its {collection.size} {collection.size === 1 ? "event stays" : "events stay"} in the feed
          </span>
          <button type="button" className="button button--small button--danger" onClick={() => remove.mutate(collection.id)}>
            Delete
          </button>
          <button type="button" className="button button--small button--quiet" onClick={() => setConfirming(false)}>
            No
          </button>
        </span>
      ) : (
        <>
          <span className="collection-row__size" data-tip={collection.size === 1 ? "1 event" : `${collection.size} events`}>
            {collection.size}
          </span>
          <IconButton icon="trash" label="Delete collection" onClick={drop} />
        </>
      )}
      {(rename.error || remove.error) && <span className="error-text tag-row__error">{errorText(rename.error ?? remove.error)}</span>}
    </li>
  );
}
