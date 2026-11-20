/** Intl formatters are slow to make and a list formats hundreds of dates and prices, so each kind is made once and reused. */
const dates = new Map<string, Intl.DateTimeFormat>();
const numbers = new Map<string, Intl.NumberFormat>();

function reused<F>(made: Map<string, F>, locale: string, options: object, make: () => F): F {
  const key = `${locale}|${JSON.stringify(options)}`;
  let formatter = made.get(key);
  if (!formatter) {
    formatter = make();
    made.set(key, formatter);
  }
  return formatter;
}

export function dateFormat(locale: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return reused(dates, locale, options, () => new Intl.DateTimeFormat(locale, options));
}

/** Throws, like Intl.NumberFormat, for an unknown currency. */
export function numberFormat(locale: string, options: Intl.NumberFormatOptions): Intl.NumberFormat {
  return reused(numbers, locale, options, () => new Intl.NumberFormat(locale, options));
}
