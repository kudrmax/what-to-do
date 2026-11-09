import { expect, it } from "vitest";

import { ApiError } from "../api/client";
import { errorText } from "./errors";

it("tells a backend refusal from a lost connection", () => {
  expect(errorText(new ApiError(409, "Сначала добавьте город"))).toBe("Сначала добавьте город");
  expect(errorText(new TypeError("Failed to fetch"))).toContain("Нет связи с приложением");
  expect(errorText(null)).toBeNull();
});
