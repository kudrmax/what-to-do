import type { EventFilters } from "./useEventFilters";

export type FeedView = "list" | "review";

const STORAGE_KEY = "feed-view";

function stored(): FeedView | null {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value === "review" || value === "list" ? value : null;
  } catch {
    return null;
  }
}

function store(view: FeedView) {
  try {
    localStorage.setItem(STORAGE_KEY, view);
  } catch {
    // Without storage the feed simply opens as a list next time.
  }
}

/** The feed as a list of days or as a review of one card at a time. It lives in the address and is remembered for the next visit. */
export function useFeedView(filters: EventFilters) {
  const fromAddress = filters.params.get("view");
  const view: FeedView = fromAddress === "review" || fromAddress === "list" ? fromAddress : (stored() ?? "list");
  const setView = (next: FeedView) => {
    store(next);
    filters.change((params) => (next === "review" ? params.set("view", next) : params.delete("view")));
  };
  return { view, setView };
}
