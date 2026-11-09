import { useState } from "react";

import { useApi } from "../api/hooks";
import { Icon } from "./Icon";
import "./EventImage.css";

interface Props {
  path: string | null;
  tag: string | undefined;
  className?: string;
}

/** The photo with the tag pinned to its corner; a portrait photo is shown whole between soft side fields. */
export function EventImage({ path, tag, className = "" }: Props) {
  const api = useApi();
  const url = api.imageUrl(path);
  const [shape, setShape] = useState<"portrait" | "landscape">("landscape");
  const [broken, setBroken] = useState(false);

  return (
    <div className={`event-image ${className}`}>
      {url && !broken ? (
        <img
          src={url}
          alt=""
          className={`event-image__photo event-image__photo--${shape}`}
          onLoad={(e) => setShape(e.currentTarget.naturalHeight > e.currentTarget.naturalWidth ? "portrait" : "landscape")}
          onError={() => setBroken(true)}
        />
      ) : (
        <Icon name="image" size={28} strokeWidth={1.6} className="event-image__placeholder" />
      )}
      {tag && <span className="event-image__tag">{tag}</span>}
    </div>
  );
}
