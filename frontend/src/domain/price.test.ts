import { expect, it } from "vitest";

import { formatPrice } from "./price";

it("writes a price for people", () => {
  expect(formatPrice(0, null)).toBe("Free");
  expect(formatPrice(1500, "RSD")?.replace(/\s/g, " ")).toBe("RSD 1,500");
  expect(formatPrice(20, "EUR")?.replace(/\s/g, " ")).toBe("EUR 20");
  expect(formatPrice(800, null)).toBe("800");
  expect(formatPrice(null, null)).toBeNull();
});
