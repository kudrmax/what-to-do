import { useState } from "react";

import { useApi } from "../api/queries";
import { EventPhoto } from "./EventPhoto";
import "./EventPhotoGrid.css";

const MOST = 5;

/** The event's photos: the main one large, up to four more beside it; one photo is shown as it always was. */
export function EventPhotoGrid({ paths, className = "" }: { paths: readonly (string | null | undefined)[]; className?: string }) {
  const [broken, setBroken] = useState<ReadonlySet<string>>(new Set());
  const shown = [...new Set(paths)].filter((path): path is string => !!path && !broken.has(path)).slice(0, MOST);
  const lose = (path: string) => setBroken((known) => new Set(known).add(path));
  if (shown.length <= 1) return <EventPhoto path={shown[0]} className={className} onBroken={() => shown[0] && lose(shown[0])} />;
  const [main, ...rest] = shown;
  return (
    <div className={`photo-grid ${className}`} data-count={shown.length}>
      <EventPhoto path={main} className="photo-grid__main" onBroken={() => lose(main)} />
      {rest.map((path) => (
        <SmallPhoto key={path} path={path} onBroken={() => lose(path)} />
      ))}
    </div>
  );
}

function SmallPhoto({ path, onBroken }: { path: string; onBroken: () => void }) {
  const url = useApi().imageUrl(path);
  if (!url) return null;
  return <img className="photo-grid__small" src={url} alt="" loading="lazy" onError={onBroken} />;
}
