/** Languages and countries by name: what the person types for a city, and what the page needs (a `lang` tag). */

const LANGUAGE_CODES = [
  "en", "es", "fr", "de", "it", "pt", "nl", "sv", "no", "nb", "da", "fi", "is", "pl", "cs", "sk", "sl", "hr", "sr", "bs", "mk", "bg", "ro",
  "hu", "el", "tr", "ru", "uk", "be", "lt", "lv", "et", "ka", "hy", "az", "kk", "uz", "he", "ar", "fa", "ur", "hi", "bn", "ta", "te", "mr",
  "th", "vi", "id", "ms", "tl", "zh", "ja", "ko", "sw", "am", "af", "ca", "eu", "gl", "ga", "cy", "sq", "mt", "lb", "mn", "ne", "si", "km",
];

const NOT_COUNTRIES = new Set(["EU", "EZ", "UN", "ZZ"]);
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

const englishNames = (type: "language" | "region") => new Intl.DisplayNames(["en"], { type, fallback: "none" });

function nativeName(code: string): string | undefined {
  try {
    return new Intl.DisplayNames([code], { type: "language", fallback: "none" }).of(code);
  } catch {
    return undefined;
  }
}

const normal = (name: string) => name.trim().toLocaleLowerCase();

/** Language names in English for the suggestions, the most common first. */
export const LANGUAGE_NAMES: string[] = [...new Set(LANGUAGE_CODES.map((code) => englishNames("language").of(code)).filter((name): name is string => Boolean(name)))];

/** Every country Intl knows by name, A to Z. */
export const COUNTRY_NAMES: string[] = Array.from(LETTERS, (a) => Array.from(LETTERS, (b) => a + b))
  .flat()
  .filter((code) => !NOT_COUNTRIES.has(code) && !/^[QX]/.test(code))
  .map((code) => englishNames("region").of(code))
  .filter((name): name is string => Boolean(name))
  .sort((a, b) => a.localeCompare(b, "en"));

/** The browser's language in English words: "English", "Spanish". */
export function browserLanguageName(preferred: readonly string[] = typeof navigator === "undefined" ? [] : navigator.languages): string {
  for (const tag of preferred) {
    try {
      const name = englishNames("language").of(new Intl.Locale(tag).language);
      if (name) return name;
    } catch {
      continue;
    }
  }
  return "English";
}

/** The `lang` tag of a language however the person wrote it: "English", "Spanish", "русский", "ru"; null when unknown. */
export function languageTag(name: string): string | null {
  const wanted = normal(name);
  if (!wanted) return null;
  for (const code of LANGUAGE_CODES) {
    const names = [code, englishNames("language").of(code), nativeName(code)];
    if (names.some((known) => known && normal(known) === wanted)) return code;
  }
  return null;
}

/** Whether a language is written in Latin letters: the browser then hyphenates Latin names in its text by itself. */
export function writesLatin(tag: string): boolean {
  try {
    return new Intl.Locale(tag).maximize().script === "Latn";
  } catch {
    return false;
  }
}
