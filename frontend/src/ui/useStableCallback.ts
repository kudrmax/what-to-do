import { useCallback, useLayoutEffect, useRef } from "react";

/** The same function for the whole life of a component that always calls the latest `fn`, so children that get it are not drawn again. */
export function useStableCallback<A extends unknown[], R>(fn: (...args: A) => R): (...args: A) => R {
  const latest = useRef(fn);
  useLayoutEffect(() => {
    latest.current = fn;
  });
  return useCallback((...args: A) => latest.current(...args), []);
}
