import { Fragment, useEffect, useRef } from "react";

import { Icon } from "../ui/Icon";

const LINK = /\s?\((https?:\/\/[^\s)]+)\)/g;

/** A post's text as it was written. Links the reader stored as "(url)" become a small link mark; this event's lines are highlighted
 * and scrolled into view. */
export function PostText({ text, highlighted }: { text: string; highlighted: number[] }) {
  const first = useRef<HTMLDivElement>(null);
  const lines = text.split("\n");
  const marked = new Set(highlighted);
  const firstMarked = highlighted.length ? Math.min(...highlighted) : -1;

  useEffect(() => {
    first.current?.scrollIntoView({ block: "center" });
  }, [text, firstMarked]);

  if (!text.trim()) return <p className="post-text__empty">В посте только фото, без текста.</p>;
  return (
    <div className="post-text">
      {lines.map((line, index) =>
        line.trim() ? (
          <div key={index} ref={index === firstMarked ? first : undefined} className={`post-text__line${marked.has(index) ? " post-text__line--marked" : ""}`}>
            <LineWithLinks line={line} />
          </div>
        ) : (
          <div key={index} className="post-text__gap" aria-hidden="true" />
        ),
      )}
    </div>
  );
}

function LineWithLinks({ line }: { line: string }) {
  const pieces: (string | { url: string })[] = [];
  let last = 0;
  for (const match of line.matchAll(LINK)) {
    pieces.push(line.slice(last, match.index), { url: match[1] });
    last = match.index + match[0].length;
  }
  pieces.push(line.slice(last));
  return (
    <>
      {pieces.map((piece, index) =>
        typeof piece === "string" ? (
          <Fragment key={index}>{piece}</Fragment>
        ) : (
          <a key={index} className="post-text__link" href={piece.url} target="_blank" rel="noreferrer" aria-label={`Ссылка: ${piece.url}`} data-tip={piece.url}>
            <Icon name="external" size={13} />
          </a>
        ),
      )}
    </>
  );
}
