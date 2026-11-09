import { expect, it } from "vitest";

import { describeRecurrence } from "./recurrence";

it("says weekly rules in words", () => {
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=TU")).toBe("Каждый вторник");
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=FR")).toBe("Каждую пятницу");
  expect(describeRecurrence("FREQ=WEEKLY;BYDAY=MO,WE,FR")).toBe("Каждый понедельник, среду и пятницу");
  expect(describeRecurrence("FREQ=DAILY")).toBe("Каждый день");
});

it("falls back to a plain word for rules it cannot say simply", () => {
  expect(describeRecurrence("FREQ=MONTHLY;BYDAY=1SA")).toBe("Повторяется");
  expect(describeRecurrence("FREQ=WEEKLY;INTERVAL=2;BYDAY=TU")).toBe("Повторяется");
  expect(describeRecurrence(null)).toBeNull();
});
