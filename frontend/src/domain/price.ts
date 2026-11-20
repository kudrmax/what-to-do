import { numberFormat } from "./formatters";
import { conventions } from "./locale";

/** "Free" for 0, "RSD 1,500" with a currency, the bare number without one; null when the price is unknown. */
export function formatPrice(price: number | null | undefined, currency: string | null | undefined): string | null {
  if (price === null || price === undefined) return null;
  if (price === 0) return "Free";
  if (!currency) return numberFormat(conventions().locale, { maximumFractionDigits: 2 }).format(price);
  try {
    return numberFormat(conventions().locale, { style: "currency", currency, currencyDisplay: "code", minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(price);
  } catch {
    return `${price} ${currency}`;
  }
}
