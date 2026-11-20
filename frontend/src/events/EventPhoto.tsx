import { useState } from "react";

import { useApi } from "../api/queries";
import "./EventPhoto.css";

/** The photo whole, on a blurred copy of itself, so posters of any shape fill the frame without cropping. */
export function EventPhoto({ path, className = "", onBroken }: { path: string | null | undefined; className?: string; onBroken?: () => void }) {
  const api = useApi();
  const url = api.imageUrl(path);
  const [broken, setBroken] = useState(false);
  if (!url || broken) return null;
  return (
    <div className={`photo ${className}`}>
      <div className="photo__backdrop" style={{ backgroundImage: `url("${url}")` }} />
      <img className="photo__image" src={url} alt="" loading="lazy" onError={() => {
          setBroken(true);
          onBroken?.();
        }} />
    </div>
  );
}
