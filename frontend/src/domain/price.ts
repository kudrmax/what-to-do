/** "Free" for 0, "RSD 1,500" with a currency, the bare number without one; null when the price is unknown. */
export function formatPrice(price: number | null | undefined, currency: string | null | undefined): string | null {
  if (price === null || price === undefined) return null;
  if (price === 0) return "Free";
  if (!currency) return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 2 }).format(price);
  try {
    return new Intl.NumberFormat("en-GB", { style: "currency", currency, currencyDisplay: "code", minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(price);
  } catch {
    return `${price} ${currency}`;
  }
}
