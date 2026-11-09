import { todayIn } from "../domain/dates";
import { useCities, useSettings } from "./queries";

/** The active city (the one in settings) and today's date in its time zone; null until a city exists. */
export function useActiveCity() {
  const settings = useSettings();
  const cities = useCities();
  const city = cities.data?.find((c) => c.id === settings.data?.active_city_id) ?? null;
  return { city, today: city ? todayIn(city.timezone) : null, loading: settings.isLoading || cities.isLoading };
}
