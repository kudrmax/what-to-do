import { useCallback, useState, type ReactNode } from "react";

import { useAnimatedClose } from "./useAnimatedClose";
import { useDismiss } from "./useDismiss";

/** A trigger and the menu it opens under itself. */
export function Popover({ trigger, children, className = "" }: { trigger: (open: boolean, toggle: () => void) => ReactNode; children: (close: () => void) => ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const { closing, startClose, onAnimationEnd } = useAnimatedClose(useCallback(() => setOpen(false), []));
  const shown = open && !closing;
  const ref = useDismiss<HTMLDivElement>(shown, startClose);
  return (
    <div className={`popover-anchor ${className}`} ref={ref} style={{ position: "relative" }}>
      {trigger(shown, () => (shown ? startClose() : setOpen(true)))}
      {open && (
        <div className={`popover${closing ? " popover--closing" : ""}`} onAnimationEnd={onAnimationEnd}>
          {children(startClose)}
        </div>
      )}
    </div>
  );
}
