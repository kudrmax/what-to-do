import { useId, useState, type FormEvent } from "react";

import { Icon } from "../ui/Icon";

/** The one question the page asks: the password the app was given, checked by decrypting the plans with it. */
export function PasswordScreen({ wrong, busy, onOpen }: { wrong: boolean; busy: boolean; onOpen: (password: string) => void }) {
  const [password, setPassword] = useState("");
  const field = useId();
  const error = useId();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (password && !busy) onOpen(password);
  };
  return (
    <main className="phone-lock">
      <div className="phone-lock__badge">
        <Icon name="lock" size={26} />
      </div>
      <h1 className="title">Plans</h1>
      <p className="phone-lock__text">Enter the password you set in What To Do.</p>
      <form className="phone-lock__form" onSubmit={submit}>
        <label className="label" htmlFor={field}>
          Password
        </label>
        <input
          id={field}
          className={`phone-input${wrong ? " phone-input--wrong" : ""}`}
          type="password"
          autoComplete="current-password"
          autoFocus
          value={password}
          aria-invalid={wrong}
          aria-describedby={wrong ? error : undefined}
          onChange={(e) => setPassword(e.target.value)}
        />
        {wrong && (
          <p id={error} className="phone-lock__error" role="alert">
            <Icon name="alert" size={16} />
            Wrong password
          </p>
        )}
        <button type="submit" className="button phone-lock__open" disabled={!password} aria-busy={busy}>
          Open
        </button>
      </form>
    </main>
  );
}
