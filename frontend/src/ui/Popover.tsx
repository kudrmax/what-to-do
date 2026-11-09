import { useState, type ReactNode } from "react";

import { useDismiss } from "./useDismiss";

/** A trigger and the menu it opens under itself. */
export function Popover({ trigger, children, className = "" }: { trigger: (open: boolean, toggle: () => void) => ReactNode; children: (close: () => void) => ReactNode; className?: string }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  const ref = useDismiss<HTMLDivElement>(open, close);
  return (
    <div className={`popover-anchor ${className}`} ref={ref} style={{ position: "relative" }}>
      {trigger(open, () => setOpen(!open))}
      {open && <div className="popover">{children(close)}</div>}
    </div>
  );
}
