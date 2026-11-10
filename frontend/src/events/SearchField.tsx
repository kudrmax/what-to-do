import { useEffect, useRef, useState } from "react";

import { Icon } from "../ui/Icon";
import "./SearchField.css";

const TYPING_PAUSE_MS = 250;

/** Search over the cards. It reaches the address once typing pauses; «/» puts the cursor in it, Esc clears it. */
export function SearchField({ value, onChange }: { value: string; onChange: (text: string) => void }) {
  const [text, setText] = useState(value);
  const input = useRef<HTMLInputElement>(null);
  const sent = useRef(value);
  const report = useRef(onChange);

  useEffect(() => {
    report.current = onChange;
  });

  useEffect(() => {
    if (value !== sent.current) {
      sent.current = value;
      setText(value);
    }
  }, [value]);

  useEffect(() => {
    if (text === sent.current) return;
    const timer = setTimeout(() => {
      sent.current = text;
      report.current(text);
    }, TYPING_PAUSE_MS);
    return () => clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    const focusOnSlash = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      const typing = target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);
      if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey) {
        event.preventDefault();
        input.current?.focus();
      }
    };
    document.addEventListener("keydown", focusOnSlash);
    return () => document.removeEventListener("keydown", focusOnSlash);
  }, []);

  const clear = () => {
    sent.current = "";
    setText("");
    onChange("");
  };

  return (
    <div className="search-field">
      <Icon name="search" size={16} className="search-field__icon" />
      <input
        ref={input}
        type="search"
        className="search-field__input"
        placeholder="Поиск"
        aria-label="Поиск по событиям"
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && text) {
            event.stopPropagation();
            clear();
          }
        }}
      />
      {text ? (
        <button type="button" className="search-field__clear" aria-label="Очистить поиск" onClick={clear}>
          <Icon name="close" size={14} />
        </button>
      ) : (
        <kbd className="search-field__hint" aria-hidden>
          /
        </kbd>
      )}
    </div>
  );
}
