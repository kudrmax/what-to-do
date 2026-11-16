import { describe, expect, it } from "vitest";

import { browserLanguageName, COUNTRY_NAMES, languageTag, LANGUAGE_NAMES, writesLatin } from "./languages";

describe("languages", () => {
  it("finds the tag of a language however it is written", () => {
    expect(languageTag("English")).toBe("en");
    expect(languageTag(" русский ")).toBe("ru");
    expect(languageTag("Russian")).toBe("ru");
    expect(languageTag("español")).toBe("es");
    expect(languageTag("de")).toBe("de");
    expect(languageTag("Klingon")).toBeNull();
  });

  it("names the browser's language in English", () => {
    expect(browserLanguageName(["es-MX", "en-US"])).toBe("Spanish");
    expect(browserLanguageName(["en-GB"])).toBe("English");
    expect(browserLanguageName([])).toBe("English");
  });

  it("tells Latin scripts from others", () => {
    expect(writesLatin("en")).toBe(true);
    expect(writesLatin("ru")).toBe(false);
    expect(writesLatin("sr")).toBe(false);
  });

  it("suggests real countries and common languages", () => {
    expect(COUNTRY_NAMES).toContain("United Kingdom");
    expect(COUNTRY_NAMES).toContain("Serbia");
    expect(COUNTRY_NAMES).not.toContain("European Union");
    expect(LANGUAGE_NAMES[0]).toBe("English");
  });
});
