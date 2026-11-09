import { todayIn } from "../domain/dates";
import { useCities } from "./hooks";

/** The active city and today's date in its time zone; null until a city exists. */
export function useActiveCity() {
  const cities = useCities();
  const city = cities.data?.find((c) => c.active) ?? null;
  return { city, today: city ? todayIn(city.timezone) : null, loading: cities.isLoading };
}
