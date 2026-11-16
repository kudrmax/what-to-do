type HourCycle = "h11" | "h12" | "h23" | "h24";

interface WeekInfo {
  firstDay: number;
}

type LocaleWithWeek = Intl.Locale & { getWeekInfo?: () => WeekInfo; weekInfo?: WeekInfo };

const MONDAY = 1;

/**
 * How the person writes dates and times, taken from the browser: the words are English like the rest of the app,
 * the order of day and month, the 12- or 24-hour clock and the first day of the week are their region's.
 */
export class LocaleConventions {
  /** The English locale dates and numbers are formatted with: the browser's own when it is English, British otherwise. */
  readonly locale: string;
  readonly hourCycle: HourCycle;
  /** The week's first day as JavaScript counts weekdays: 0 is Sunday, 1 Monday. */
  readonly firstDay: number;

  constructor(browserLocale: string) {
    const browser = LocaleConventions.valid(browserLocale) ?? "en-GB";
    this.locale = browser.split("-")[0].toLowerCase() === "en" ? browser : "en-GB";
    this.hourCycle = (new Intl.DateTimeFormat(browser, { hour: "numeric" }).resolvedOptions().hourCycle as HourCycle | undefined) ?? "h23";
    this.firstDay = LocaleConventions.weekStart(browser);
  }

  static fromBrowser(): LocaleConventions {
    return new LocaleConventions(typeof navigator === "undefined" ? "en-GB" : (navigator.languages?.[0] ?? navigator.language));
  }

  private static valid(tag: string | undefined): string | null {
    if (!tag) return null;
    try {
      return Intl.getCanonicalLocales(tag)[0] ?? null;
    } catch {
      return null;
    }
  }

  /** Intl counts 1 for Monday to 7 for Sunday; browsers without week data start on Monday. */
  private static weekStart(tag: string): number {
    try {
      const locale = new Intl.Locale(tag).maximize() as LocaleWithWeek;
      const info = locale.getWeekInfo?.() ?? locale.weekInfo;
      return info ? info.firstDay % 7 : MONDAY;
    } catch {
      return MONDAY;
    }
  }
}

let current = LocaleConventions.fromBrowser();

export const conventions = (): LocaleConventions => current;

/** Tests pin the conventions, so what they expect does not depend on the machine's locale. */
export function setConventions(next: LocaleConventions): void {
  current = next;
}
