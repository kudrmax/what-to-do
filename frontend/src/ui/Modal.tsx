import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./IconButton";
import "./Modal.css";

/** A window over the screen: closes with the cross, Esc or a click outside, and keeps the page under it still. */
export function Modal({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return createPortal(
    <div className="modal" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="modal__window" role="dialog" aria-modal="true" aria-label={label}>
        <IconButton icon="close" label="Закрыть" className="modal__close" onClick={onClose} />
        {children}
      </div>
    </div>,
    document.body,
  );
}
