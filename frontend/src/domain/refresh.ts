import type { RefreshStatus } from "../api/client";

interface Count {
  done: number;
  total: number;
}

const PACE_AFTER = { items: 3, seconds: 5 };

/** What the current stage is counting: sites' pages take the collecting stage over once they are being downloaded. */
function count(status: RefreshStatus): Count | null {
  switch (status.stage) {
    case "idle":
    case "collecting":
      return status.pages_to_fetch > 0
        ? { done: status.pages_fetched, total: status.pages_to_fetch }
        : { done: status.sources_collected, total: status.sources_to_collect };
    case "photos":
      return { done: status.photos_read, total: status.photos_to_read };
    case "reading":
      return { done: status.posts_read, total: status.posts_to_read };
    case "merging":
      return { done: status.announcements_merged, total: status.announcements_to_merge };
    default:
      return null;
  }
}

const STAGE_NAME: Record<RefreshStatus["stage"], string> = {
  idle: "Collecting sources",
  collecting: "Collecting sources",
  photos: "Reading photos",
  reading: "Reading posts and pages",
  merging: "Merging duplicates",
  done: "Done",
  failed: "Something went wrong",
};

export function refreshLabel(status: RefreshStatus | undefined): string {
  if (!status) return STAGE_NAME.collecting;
  const counted = count(status);
  const collectingPages = (status.stage === "collecting" || status.stage === "idle") && status.pages_to_fetch > 0;
  const name = collectingPages ? "Downloading site pages" : STAGE_NAME[status.stage];
  return counted && counted.total > 0 ? `${name}: ${counted.done} of ${counted.total}` : name;
}

/** How long the current stage still needs at the pace it has kept so far; null until that pace is known. */
export function timeLeft(status: RefreshStatus | undefined, now: Date = new Date()): string | null {
  const counted = status && count(status);
  if (!status?.stage_started_at || !counted || counted.done >= counted.total) return null;
  const elapsed = (now.getTime() - Date.parse(status.stage_started_at)) / 1000;
  if (counted.done < PACE_AFTER.items || elapsed < PACE_AFTER.seconds) return null;
  const seconds = (elapsed / counted.done) * (counted.total - counted.done);
  return seconds < 60 ? "less than a minute" : `~${Math.round(seconds / 60)} min left`;
}
