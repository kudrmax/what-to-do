import { useCallback, useEffect, useRef, useState, type AnimationEvent } from "react";

/** Longer than any closing animation: the window closes anyway where animations do not run. */
const CLOSE_FALLBACK_MS = 250;

/**
 * Something that plays its closing animation before it goes (a window, a menu): `startClose`
 * marks it closing, and `onClose` runs when the root's animation ends. It can open and close again.
 */
export function useAnimatedClose(onClose: () => void) {
  const [closing, setClosing] = useState(false);
  const closed = useRef(false);
  const finish = useCallback(() => {
    if (closed.current) return;
    closed.current = true;
    setClosing(false);
    onClose();
  }, [onClose]);
  const startClose = useCallback(() => {
    closed.current = false;
    setClosing(true);
  }, []);

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
