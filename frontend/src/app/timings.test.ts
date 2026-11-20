import { describe, expect, it } from "vitest";

import { InterfaceTimings, type InterfaceTiming } from "./timings";

describe("InterfaceTimings", () => {
  it("reports an action with its phases once the page has drawn it", async () => {
    const sent: InterfaceTiming[] = [];
    const timings = new InterfaceTimings();
    timings.connect((timing) => sent.push(timing));
    const measurement = timings.start("mark");
    measurement.phase("saved");
    await measurement.finish();
    timings.disconnect();
    expect(sent).toHaveLength(1);
    expect(sent[0].action).toBe("mark");
    expect(Object.keys(sent[0].phases)).toEqual(["saved", "shown"]);
    expect(sent[0].phases.shown).toBeGreaterThanOrEqual(sent[0].phases.saved);
  });

});
