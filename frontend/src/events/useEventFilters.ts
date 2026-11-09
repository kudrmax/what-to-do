import { useSearchParams } from "react-router-dom";

import type { FeedQuery } from "../api/client";

type Shared = Pick<FeedQuery, "tags" | "sources" | "only_timed" | "hide_multiday">;

/** The filters every list of events shares. They live in the address, under the API's own names. */
export function useEventFilters() {
  const [params, setParams] = useSearchParams();
  const change = (edit: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    edit(next);
    setParams(next, { replace: true });
  };
  const flag = (name: keyof Shared) => params.get(name) === "true";
  const query: Shared = {
    tags: params.getAll("tags"),
    sources: params.getAll("sources").map(Number),
    only_timed: flag("only_timed"),
    hide_multiday: flag("hide_multiday"),
  };
  return {
    query,
    params,
    change,
    setList: (name: "tags" | "sources", values: (string | number)[]) =>
      change((next) => {
        next.delete(name);
        values.forEach((value) => next.append(name, String(value)));
      }),
    setFlag: (name: "only_timed" | "hide_multiday", on: boolean) => change((next) => (on ? next.set(name, "true") : next.delete(name))),
  };
}

export type EventFilters = ReturnType<typeof useEventFilters>;
