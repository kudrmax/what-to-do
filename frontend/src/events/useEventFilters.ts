import { useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import type { FeedQuery } from "../api/client";

type Shared = Pick<FeedQuery, "tags" | "sources" | "only_timed" | "hide_multiday" | "only_priority" | "search">;

/** The filters that stay as they were when the user moves to another screen or opens the app again. The search is a passing look and is not kept. */
const KEPT = ["tags", "sources", "only_timed", "hide_multiday", "only_priority"] as const;
const STORAGE_KEY = "event-filters";

function kept(params: URLSearchParams): URLSearchParams {
  const result = new URLSearchParams();
  params.forEach((value, key) => {
    if ((KEPT as readonly string[]).includes(key)) result.append(key, value);
  });
  return result;
}

function remembered(): URLSearchParams {
  try {
    return kept(new URLSearchParams(localStorage.getItem(STORAGE_KEY) ?? ""));
  } catch {
    return new URLSearchParams();
  }
}

function remember(params: URLSearchParams) {
  try {
    localStorage.setItem(STORAGE_KEY, kept(params).toString());
  } catch {
    // Without storage the filters last until the screen changes.
  }
}

/** An address without any kept filter takes the remembered ones; an address that names some is the user's choice. */
function withRemembered(params: URLSearchParams): URLSearchParams {
  if (kept(params).size > 0) return params;
  const next = new URLSearchParams(params);
  remembered().forEach((value, key) => next.append(key, value));
  return next;
}

/** The same filters give the same object, so the lists they are passed to are not drawn again for nothing. */
function filtersOf(params: URLSearchParams): Shared {
  const flag = (name: keyof Shared) => params.get(name) === "true";
  return {
    tags: params.getAll("tags"),
    sources: params.getAll("sources").map(Number),
    only_timed: flag("only_timed"),
    hide_multiday: flag("hide_multiday"),
    only_priority: flag("only_priority"),
    search: params.get("search") ?? "",
  };
}

/** The filters every list of events shares. They live in the address, under the API's own names, and are remembered across screens and launches. */
export function useEventFilters() {
  const [address, setParams] = useSearchParams();
  const params = withRemembered(address);
  const restoring = params.toString() !== address.toString();
  useEffect(() => {
    if (restoring) setParams(params, { replace: true });
  });
  const change = (edit: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    edit(next);
    remember(next);
    setParams(next, { replace: true });
  };
  const current = params.toString();
  const query = useMemo(() => filtersOf(new URLSearchParams(current)), [current]);
  return {
    query,
    params,
    change,
    setList: (name: "tags" | "sources", values: (string | number)[]) =>
      change((next) => {
        next.delete(name);
        values.forEach((value) => next.append(name, String(value)));
      }),
    setFlag: (name: "only_timed" | "hide_multiday" | "only_priority", on: boolean) => change((next) => (on ? next.set(name, "true") : next.delete(name))),
    setSearch: (text: string) => change((next) => (text.trim() ? next.set("search", text) : next.delete("search"))),
  };
}

export type EventFilters = ReturnType<typeof useEventFilters>;
