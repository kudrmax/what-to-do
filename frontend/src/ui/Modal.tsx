import { useEffect, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./IconButton";
import { useAnimatedClose } from "./useAnimatedClose";
import "./Modal.css";

/** A window over the screen: closes with the cross, Esc or a click outside, and keeps the page under it still. */
export function Modal({ label, onClose, children, className = "" }: { label: string; onClose: () => void; children: ReactNode; className?: string }) {
  const { closing, startClose, onAnimationEnd } = useAnimatedClose(onClose);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && startClose();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [startClose]);

  return createPortal(
    <div className={`modal${closing ? " modal--closing" : ""}`} onMouseDown={(event) => event.target === event.currentTarget && startClose()} onAnimationEnd={onAnimationEnd}>
      <div className={`modal__window ${className}`} role="dialog" aria-modal="true" aria-label={label}>
        <IconButton icon="close" label="Закрыть" className="modal__close" onClick={startClose} />
        {children}
      </div>
    </div>,
    document.body,
  );
}
