import { useState } from "react";

import type { City } from "../api/client";
import { useAddCity, useChangeCity, useChangeSettings, useCities, useCityContents, useDeleteCity, useSettings } from "../api/queries";
import { plural } from "../domain/dates";
import { errorText } from "../ui/errors";
import { Icon, type IconName } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { Modal } from "../ui/Modal";
import { Section } from "../ui/Screen";
import { CityForm } from "./CityForm";
import "./Cities.css";

export function CitiesSection() {
  const cities = useCities();
  const settings = useSettings();
  const [adding, setAdding] = useState(false);
  const list = cities.data ?? [];
  return (
    <Section title="Cities" hint="Upcoming, Calendar and Sources show the selected city. Add another one when you travel or move: each city keeps its own sources and cards.">
      {list.length > 0 && (
        <ul className="city-list" aria-label="Cities">
          {list.map((city) => (
            <CityRow key={city.id} city={city} active={city.id === settings.data?.active_city_id} />
          ))}
        </ul>
      )}
      {adding || list.length === 0 ? (
        <NewCity onDone={() => setAdding(false)} canCancel={list.length > 0} />
      ) : (
        <button type="button" className="chip chip--dashed city-list__add" onClick={() => setAdding(true)}>
          <Icon name="plus" size={14} />
          Add city
        </button>
      )}
    </Section>
  );
}

export function NewCity({ onDone, canCancel }: { onDone?: () => void; canCancel: boolean }) {
  const add = useAddCity();
  return <CityForm submitLabel="Add city" busy={add.isPending} error={add.error} onSubmit={(city) => add.mutate(city, { onSuccess: onDone })} onCancel={canCancel ? onDone : undefined} />;
}

function CityRow({ city, active }: { city: City; active: boolean }) {
  const select = useChangeSettings();
  const change = useChangeCity();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  if (editing) {
    return (
      <li className="city-row city-row--editing">
        <CityForm
          city={city}
          submitLabel="Save"
          busy={change.isPending}
          error={change.error}
          onSubmit={(fields) => change.mutate({ id: city.id, change: fields }, { onSuccess: () => setEditing(false) })}
          onCancel={() => (change.reset(), setEditing(false))}
        />
      </li>
    );
  }
  return (
    <li className={`city-row${active ? " city-row--active" : ""}`}>
      <button
        type="button"
        className="city-row__select"
        role="radio"
        aria-checked={active}
        aria-label={active ? `${city.name} is shown` : `Show ${city.name}`}
        data-tip={active ? "Shown now" : "Show this city"}
        onClick={() => !active && select.mutate({ active_city_id: city.id })}
      >
        <span className="city-row__radio" />
      </button>
      <div className="city-row__place">
        <span className="city-row__name">{city.name}</span>
        {city.country ? (
          <span className="city-row__country">{city.country}</span>
        ) : (
          <button type="button" className="city-row__missing" onClick={() => setEditing(true)}>
            <Icon name="alert" size={14} />
            Add the country
          </button>
        )}
      </div>
      <Fact icon="clock" label="Time zone" value={city.timezone.replaceAll("_", " ")} />
      <Fact icon="language" label="Language of event cards" value={city.card_language} />
      <span className="city-row__actions">
        <IconButton icon="pencil" label={`Edit ${city.name}`} onClick={() => setEditing(true)} />
        <IconButton icon="trash" label={`Delete ${city.name}`} onClick={() => setDeleting(true)} />
      </span>
      {deleting && <DeleteCityDialog city={city} onClose={() => setDeleting(false)} />}
    </li>
  );
}

function Fact({ icon, label, value }: { icon: IconName; label: string; value: string }) {
  return (
    <span className="city-row__fact" data-tip={label}>
      <Icon name={icon} size={15} className="city-row__fact-icon" />
      <span className="visually-hidden">{label}: </span>
      {value}
    </span>
  );
}

function DeleteCityDialog({ city, onClose }: { city: City; onClose: () => void }) {
  const remove = useDeleteCity();
  const contents = useCityContents(city.id, !remove.isPending && !remove.isSuccess);
  const counts = contents.data;
  return (
    <Modal label={`Delete ${city.name}`} onClose={onClose} className="city-delete">
      <h2 className="city-delete__title">Delete {city.name}?</h2>
      <p className="city-delete__text">Everything collected for this city goes with it:</p>
      {counts ? (
        <ul className="city-delete__counts">
          <Count icon="send" count={counts.sources} one="source" other="sources" note={plural(counts.sources, "with its posts", "with their posts")} />
          <Count icon="calendar" count={counts.events} one="event" other="events" />
          <Count icon="star" count={counts.marked_events} one="event you marked" other="events you marked" />
        </ul>
      ) : (
        <p className="city-delete__text">{contents.isError ? errorText(contents.error) : "Counting…"}</p>
      )}
      <p className="city-delete__warning">
        <Icon name="alert" size={16} />
        This can’t be undone.
      </p>
      {remove.error ? <p className="error-text">{errorText(remove.error)}</p> : null}
      <div className="city-delete__actions">
        <button type="button" className="button button--quiet" onClick={onClose}>
          Cancel
        </button>
        <button type="button" className="button button--danger" disabled={remove.isPending || !counts} onClick={() => remove.mutate(city.id, { onSuccess: onClose })}>
          Delete city
        </button>
      </div>
    </Modal>
  );
}

function Count({ icon, count, one, other, note }: { icon: IconName; count: number; one: string; other: string; note?: string }) {
  return (
    <li className="city-delete__count">
      <Icon name={icon} size={16} className="city-delete__icon" />
      <span className="city-delete__number">{count}</span>
      <span>{plural(count, one, other)}</span>
      {note && <span className="city-delete__note">{note}</span>}
    </li>
  );
}
