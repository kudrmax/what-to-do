import { expect, it } from "vitest";

import { formatPrice } from "./price";

it("writes a price for people", () => {
  expect(formatPrice(0, null)).toBe("Бесплатно");
  expect(formatPrice(1500, "RSD")?.replace(/\s/g, " ")).toBe("1 500 RSD");
  expect(formatPrice(20, "EUR")?.replace(/\s/g, " ")).toBe("20 EUR");
  expect(formatPrice(800, null)).toBe("800");
  expect(formatPrice(null, null)).toBeNull();
});
