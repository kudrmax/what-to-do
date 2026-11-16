import { todayIn } from "../domain/dates";
import { languageTag, writesLatin } from "../domain/languages";
import { softHyphenate } from "../ui/softHyphens";
import { useCities, useSettings } from "./queries";

/** The active city (the one in settings) and today's date in its time zone; null until a city exists. */
export function useActiveCity() {
  const settings = useSettings();
  const cities = useCities();
  const city = cities.data?.find((c) => c.id === settings.data?.active_city_id) ?? null;
  return { city, today: city ? todayIn(city.timezone) : null, loading: settings.isLoading || cities.isLoading };
}

/** The language the active city's cards are written in: its `lang` tag, and how its long Latin words may break. */
export function useCardLanguage(): { lang: string | undefined; hyphenate: (text: string) => string } {
  const { city } = useActiveCity();
  const lang = (city && languageTag(city.card_language)) ?? undefined;
  const foreignScript = lang !== undefined && !writesLatin(lang);
  return { lang, hyphenate: (text) => (foreignScript ? softHyphenate(text) : text) };
}
