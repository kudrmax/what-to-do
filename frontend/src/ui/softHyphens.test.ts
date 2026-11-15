import { describe, expect, it } from "vitest";
import { softHyphenate } from "./softHyphens";

const visible = (text: string) => text.replaceAll("­", "-");

describe("softHyphenate", () => {
  it("breaks Latin words between syllables", () => {
    expect(visible(softHyphenate("Songwriting as Storytelling"))).toBe("Song-wri-ting as Sto-ry-tel-ling");
    expect(visible(softHyphenate("Shcherbakova"))).toBe("Shcher-ba-kova");
    expect(visible(softHyphenate("Avoidfest"))).toBe("Avoid-fest");
  });

  it("keeps sh, ch, th and the like together", () => {
    expect(visible(softHyphenate("Washington"))).toBe("Wa-shing-ton");
  });

  it("covers Serbian Latin letters", () => {
    expect(visible(softHyphenate("Marjanović"))).toBe("Mar-ja-no-vić");
    expect(visible(softHyphenate("Unutrašnjosti"))).toBe("Unut-raš-njosti");
  });

  it("leaves short words and Cyrillic text as they are", () => {
    expect(softHyphenate("Earth Works: экскурсия по выставке")).toBe("Earth Works: экскурсия по выставке");
  });
});
