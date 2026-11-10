import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

import { useApi } from "../api/queries";
import { IconButton } from "../ui/IconButton";
import "./PhotoViewer.css";

export interface ViewedPhoto {
  url: string;
  text: string | null;
}

/** Photos one by one, each beside the text Claude read on it. Over the event window: Esc closes only the viewer. */
export function PhotoViewer({ photos, start, onClose }: { photos: ViewedPhoto[]; start: number; onClose: () => void }) {
  const api = useApi();
  const [index, setIndex] = useState(start);
  const count = photos.length;
  const photo = photos[index];
  const step = (by: number) => setIndex((current) => (current + by + count) % count);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const keys: Record<string, () => void> = { Escape: onClose, ArrowLeft: () => step(-1), ArrowRight: () => step(1) };
      if (!keys[event.key]) return;
      event.stopImmediatePropagation();
      keys[event.key]();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });

  return createPortal(
    <div className="viewer" role="dialog" aria-modal="true" aria-label="Просмотр фото" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="viewer__stage">
        {count > 1 && <IconButton icon="chevronLeft" label="Предыдущее фото" className="viewer__step" onClick={() => step(-1)} />}
        <img className="viewer__image" src={api.imageUrl(photo.url) ?? undefined} alt={`Фото ${index + 1} из ${count}`} />
        {count > 1 && <IconButton icon="chevronRight" label="Следующее фото" className="viewer__step" onClick={() => step(1)} />}
      </div>
      <aside className="viewer__panel">
        <div className="viewer__head">
          <span className="label">
            Фото {index + 1} из {count}
          </span>
          <IconButton icon="close" label="Закрыть просмотр" onClick={onClose} />
        </div>
        <h3 className="viewer__title">Текст, который Claude прочитал на фото</h3>
        <p className={`viewer__text${photo.text ? "" : " viewer__text--none"}`}>{photo.text === null ? "Текст с этого фото ещё не прочитан." : photo.text || "На фото нет текста."}</p>
      </aside>
    </div>,
    document.body,
  );
}
