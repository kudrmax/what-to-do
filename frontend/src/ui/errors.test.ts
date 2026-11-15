import { expect, it } from "vitest";

import { ApiError } from "../api/client";
import { errorText } from "./errors";

it("tells a backend refusal from a lost connection", () => {
  expect(errorText(new ApiError(409, "Add a city first"))).toBe("Add a city first");
  expect(errorText(new TypeError("Failed to fetch"))).toContain("Can’t reach the app");
  expect(errorText(null)).toBeNull();
});
