const AMBIGUOUS_NAME = /^@?[A-Za-z][A-Za-z0-9_]{3,31}$/;

/** A bare name that could be a Telegram channel or an Instagram profile, so the user has to say which. */
export function ambiguousName(link: string): boolean {
  return AMBIGUOUS_NAME.test(link.trim());
}
