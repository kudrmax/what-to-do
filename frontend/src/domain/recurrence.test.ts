import { expect, it } from "vitest";

import { describeRecurrence } from "./recurrence";

it("says weekly rules in words", () => {
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=TU")).toBe("Every Tuesday");
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=FR")).toBe("Every Friday");
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=MO,WE,FR")).toBe("Every Monday, Wednesday and Friday");
  expect(describeRecurrence("FREQ=DAILY")).toBe("Every day");
});

it("falls back to a plain word for rules it cannot say simply", () => {
  expect(describeRecurrence("FREQ=MONTHLY;BYDAY=1SA")).toBe("Repeats");
  expect(describeRecurrence("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU")).toBe("Repeats");
  expect(describeRecurrence(null)).toBeNull();
});
