import { useState } from "react";

const COPY_LABELS = { idle: "Copy", copied: "Copied", failed: "Couldn’t copy" } as const;

/** Copies a text to the clipboard; `label` says what happened for the Copy button. */
export function useCopy(text: string) {
  const [state, setState] = useState<keyof typeof COPY_LABELS>("idle");
  const copy = () => {
    if (!navigator.clipboard) return setState("failed");
    navigator.clipboard.writeText(text).then(
      () => setState("copied"),
      () => setState("failed"),
    );
  };
  return { copy, copied: state === "copied", label: COPY_LABELS[state] };
}
