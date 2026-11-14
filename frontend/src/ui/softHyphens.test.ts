import { describe, expect, it } from "vitest";
import { softHyphenate } from "./softHyphens";

const visible = (text: string) => text.replaceAll("­", "-");

describe("softHyphenate", () => {
  it("allows a break anywhere in a long Latin word but keeps three letters on each side", () => {
    expect(visible(softHyphenate("Shcherbakova"))).toBe("Shc-h-e-r-b-a-k-ova");
  });

  it("covers Serbian Latin letters", () => {
    expect(visible(softHyphenate("Marjanović"))).toBe("Mar-j-a-n-o-vić");
  });

  it("leaves short words and Cyrillic text as they are", () => {
    expect(softHyphenate("Earth Works: экскурсия по выставке")).toBe("Earth Works: экскурсия по выставке");
  });
});
