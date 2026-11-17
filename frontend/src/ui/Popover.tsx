import { useCallback, useLayoutEffect, useRef, useState, type ReactNode } from "react";

import { useAnimatedClose } from "./useAnimatedClose";
import { useDismiss } from "./useDismiss";

/** A trigger and the menu it opens under itself. */
export function Popover({
  trigger,
  children,
  className = "",
  align = "start",
}: {
  trigger: (open: boolean, toggle: () => void) => ReactNode;
  children: (close: () => void) => ReactNode;
  className?: string;
  align?: "start" | "end";
}) {
  const [open, setOpen] = useState(false);
  const { closing, startClose, onAnimationEnd } = useAnimatedClose(useCallback(() => setOpen(false), []));
  const shown = open && !closing;
  const ref = useDismiss<HTMLDivElement>(shown, startClose);
  const menu = useRef<HTMLDivElement>(null);
  const [atEnd, setAtEnd] = useState(false);
  useLayoutEffect(() => {
    if (!open) return setAtEnd(false);
    const box = menu.current?.getBoundingClientRect();
    if (box && box.right > document.documentElement.clientWidth - 8) setAtEnd(true);
  }, [open]);
  return (
    <div className={`popover-anchor ${className}`} ref={ref} style={{ position: "relative" }}>
      {trigger(shown, () => (shown ? startClose() : setOpen(true)))}
      {open && (
        <div ref={menu} className={`popover${atEnd || align === "end" ? " popover--end" : ""}${closing ? " popover--closing" : ""}`} onAnimationEnd={onAnimationEnd}>
          {children(startClose)}
        </div>
      )}
    </div>
  );
}
