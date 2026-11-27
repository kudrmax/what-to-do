import { useId, useState, type FormEvent } from "react";

import type { City, NewCity } from "../api/client";
import { useReader } from "../api/useReader";
import { browserLanguageName, COUNTRY_NAMES, LANGUAGE_NAMES } from "../domain/languages";
import { errorText } from "../ui/errors";
import "./Cities.css";

const ZONES = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : [];

const sameText = (a: string, b: string) => a.trim().toLocaleLowerCase() === b.trim().toLocaleLowerCase();

interface Props {
  /** The city being edited; a new one starts from the browser's time zone and language. */
  city?: City;
  submitLabel: string;
  busy: boolean;
  error: unknown;
  onSubmit: (city: NewCity) => void;
  onCancel?: () => void;
}

/** A city's four facts, each with what it is for: the name and the country, its clock, the language of its cards. */
export function CityForm({ city, submitLabel, busy, error, onSubmit, onCancel }: Props) {
  const ids = useId();
  const reader = useReader();
  const [name, setName] = useState(city?.name ?? "");
  const [country, setCountry] = useState(city?.country ?? "");
  const [timezone, setTimezone] = useState(city?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [language, setLanguage] = useState(city?.card_language ?? browserLanguageName());
  const ready = [name, country, timezone, language].every((value) => value.trim());
  const languageChanged = city !== undefined && !sameText(language, city.card_language) && language.trim() !== "";
  const submit = (event: FormEvent) => {
    event.preventDefault();
    onSubmit({ name: name.trim(), country: country.trim(), timezone: timezone.trim(), card_language: language.trim() });
  };
  return (
    <form className="city-form" onSubmit={submit}>
      <div className="city-form__fields">
        <div className="city-form__field">
          <label className="label" htmlFor={`${ids}-name`}>
            City
          </label>
          <input id={`${ids}-name`} className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="City name" autoFocus required />
        </div>
        <div className="city-form__field">
          <label className="label" htmlFor={`${ids}-country-input`}>
            Country
          </label>
          <input id={`${ids}-country-input`} className="input" value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Country" list={`${ids}-countries`} required aria-describedby={`${ids}-country`} />
          <span id={`${ids}-country`} className="city-form__hint">
            Tells apart cities of the same name and finds places on the map
          </span>
          <datalist id={`${ids}-countries`}>
            {COUNTRY_NAMES.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </div>
        <div className="city-form__field">
          <label className="label" htmlFor={`${ids}-zone-input`}>
            Time zone
          </label>
          <input id={`${ids}-zone-input`} className="input" value={timezone} onChange={(e) => setTimezone(e.target.value)} list={`${ids}-zones`} required aria-describedby={`${ids}-zone`} />
          <span id={`${ids}-zone`} className="city-form__hint">
            Today and the event times are counted in it
          </span>
          <datalist id={`${ids}-zones`}>
            {ZONES.map((zone) => (
              <option key={zone} value={zone} />
            ))}
          </datalist>
        </div>
        <div className="city-form__field">
          <label className="label" htmlFor={`${ids}-language-input`}>
            Language of event cards
          </label>
          <input id={`${ids}-language-input`} className="input" value={language} onChange={(e) => setLanguage(e.target.value)} list={`${ids}-languages`} required aria-describedby={`${ids}-language`} />
          <span id={`${ids}-language`} className={`city-form__hint${languageChanged ? " city-form__hint--note" : ""}`}>
            {languageChanged ? "The next refresh rewrites the recent cards in this language" : `${reader.name} writes card titles and descriptions in it`}
          </span>
          <datalist id={`${ids}-languages`}>
            {LANGUAGE_NAMES.map((option) => (
              <option key={option} value={option} />
            ))}
          </datalist>
        </div>
      </div>
      <div className="city-form__actions">
        {error ? <p className="error-text city-form__error">{errorText(error)}</p> : null}
        {onCancel && (
          <button type="button" className="button button--quiet" onClick={onCancel}>
            Cancel
          </button>
        )}
        <button type="submit" className="button" disabled={busy || !ready}>
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
