import { useCallback, useEffect, useRef, useState, type AnimationEvent } from "react";

/** Longer than any closing animation: the window closes anyway where animations do not run. */
const CLOSE_FALLBACK_MS = 250;

/**
 * A window that plays its closing animation before it goes: `startClose` marks it closing,
 * and `onClose` runs when the root's animation ends.
 */
export function useAnimatedClose(onClose: () => void) {
  const [closing, setClosing] = useState(false);
  const closed = useRef(false);
  const finish = useCallback(() => {
    if (closed.current) return;
    closed.current = true;
    onClose();
  }, [onClose]);
  const startClose = useCallback(() => setClosing(true), []);

  useEffect(() => {
    if (!closing) return;
    const timer = window.setTimeout(finish, CLOSE_FALLBACK_MS);
    return () => window.clearTimeout(timer);
  }, [closing, finish]);

  const onAnimationEnd = (event: AnimationEvent) => {
    if (closing && event.target === event.currentTarget) finish();
  };

  return { closing, startClose, onAnimationEnd };
}
