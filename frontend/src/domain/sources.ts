import type { Mention } from "../api/client";

const AMBIGUOUS_NAME = /^@?[A-Za-z][A-Za-z0-9_]{3,31}$/;

/** A bare name that could be a Telegram channel or an Instagram profile, so the user has to say which. */
export function ambiguousName(link: string): boolean {
  return AMBIGUOUS_NAME.test(link.trim());
}

export type OriginalPlace = "website" | "telegram" | "instagramPost" | "instagramHighlight";

/** Where the link to a post leads: a page on the source's website, a Telegram post, an Instagram post or highlight. */
export function originalPlace(mention: Pick<Mention, "source_kind" | "post_url">): OriginalPlace {
  if (mention.source_kind === "web") return "website";
  if (mention.source_kind === "telegram") return "telegram";
  return mention.post_url.includes("/stories/highlights/") ? "instagramHighlight" : "instagramPost";
}
