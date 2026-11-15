import { useState, type FormEvent } from "react";

import type { EventCard } from "../api/client";
import { useAddDevNote } from "../api/queries";
import { Icon } from "../ui/Icon";
import { Modal } from "../ui/Modal";
import "./DevNoteButton.css";

/** The developer's own inbox of ideas about a card: the text is only saved, the app never shows it back. */
export function DevNoteButton({ event, size }: { event: EventCard; size: "small" | "large" }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);
  return (
    <>
      <button type="button" className={`dev-note__button dev-note__button--${size}`} aria-label="Note to developer" data-tip="Note to developer" aria-expanded={open} onClick={() => setOpen(true)}>
        <Icon name="comment" size={size === "small" ? 14 : 18} strokeWidth={2} />
      </button>
      {open && (
        <Modal label="Note to developer" className="dev-note__window" onClose={close}>
          <DevNoteForm event={event} onDone={close} />
        </Modal>
      )}
    </>
  );
}

function DevNoteForm({ event, onDone }: { event: EventCard; onDone: () => void }) {
  const [text, setText] = useState("");
  const add = useAddDevNote();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) add.mutate({ id: event.id, text }, { onSuccess: onDone });
  };
  return (
    <form className="dev-note__form" onSubmit={submit}>
      <h2 className="dev-note__title">{event.title}</h2>
      <textarea
        className="input dev-note__text"
        aria-label="Note text"
        placeholder="What to improve"
        rows={5}
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && (e.metaKey || e.ctrlKey) && submit(e)}
      />
      {add.isError && <p className="error-text">Couldn’t save. Try again.</p>}
      <button type="submit" className="button" disabled={!text.trim() || add.isPending}>
        Save
      </button>
    </form>
  );
}
