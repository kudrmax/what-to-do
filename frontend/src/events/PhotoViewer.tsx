import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { useApi } from "../api/queries";
import { IconButton } from "../ui/IconButton";
import { useAnimatedClose } from "../ui/useAnimatedClose";
import "./PhotoViewer.css";

export interface ViewedPhoto {
  url: string;
  text: string | null;
}

/** Photos one by one, each beside the text read on it. Over the event window: Esc closes only the viewer. */
export function PhotoViewer({ photos, start, onClose }: { photos: ViewedPhoto[]; start: number; onClose: () => void }) {
  const api = useApi();
  const [index, setIndex] = useState(start);
  const count = photos.length;
  const photo = photos[index];
  const step = (by: number) => setIndex((current) => (current + by + count) % count);
  const { closing, startClose, onAnimationEnd } = useAnimatedClose(onClose);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const keys: Record<string, () => void> = { Escape: startClose, ArrowLeft: () => step(-1), ArrowRight: () => step(1) };
      if (!keys[event.key]) return;
      event.stopImmediatePropagation();
      keys[event.key]();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  return createPortal(
    <div className={`viewer${closing ? " viewer--closing" : ""}`} role="dialog" aria-modal="true" aria-label="Photo viewer" onMouseDown={(event) => event.target === event.currentTarget && startClose()} onAnimationEnd={onAnimationEnd}>
      <div className="viewer__stage">
        {count > 1 && <IconButton icon="chevronLeft" label="Previous photo" className="viewer__step" onClick={() => step(-1)} />}
        <img className="viewer__image" src={api.imageUrl(photo.url) ?? undefined} alt={`Photo ${index + 1} of ${count}`} />
        {count > 1 && <IconButton icon="chevronRight" label="Next photo" className="viewer__step" onClick={() => step(1)} />}
      </div>
      <aside className="viewer__panel">
        <div className="viewer__head">
          <span className="label">
            Photo {index + 1} of {count}
          </span>
          <IconButton icon="close" label="Close viewer" onClick={startClose} />
        </div>
        <h3 className="viewer__title">Text read in the photo</h3>
        <p className={`viewer__text${photo.text ? "" : " viewer__text--none"}`}>{photo.text === null ? "The text in this photo hasn’t been read yet." : photo.text || "There’s no text in this photo."}</p>
      </aside>
    </div>,
    document.body,
  );
}
