import { useState, type FormEvent } from "react";

import { useClaudeSignIn } from "../api/queries";
import { Icon } from "../ui/Icon";
import { errorText } from "../ui/errors";

/** Shown under Refresh when Claude has no login: signs in through the browser, no terminal needed. */
export function ClaudeSignIn() {
  const signIn = useClaudeSignIn();
  const status = signIn.status;

  if (status?.state === "signed_in") {
    return (
      <div className="note claude-sign-in claude-sign-in--done" role="status">
        <strong className="claude-sign-in__title">
          <Icon name="check" size={16} strokeWidth={2.4} />
          Signed in to Claude
        </strong>
        <span>Press Refresh to read the posts.</span>
      </div>
    );
  }

  if (status?.signing_in) {
    return (
      <div className="note claude-sign-in" role="status">
        <strong className="claude-sign-in__title">
          <span className="spinner" />
          Finish signing in in your browser
        </strong>
        <span>Come back here once the page says you’re signed in.</span>
        {status.page_url && (
          <CodeFallback pageUrl={status.page_url} onSubmit={signIn.submitCode} submitting={signIn.submitting} error={signIn.codeError} cliError={status.error ?? null} />
        )}
      </div>
    );
  }

  return (
    <div className="note claude-sign-in" role="alert">
      <strong className="claude-sign-in__title">Sign in to Claude to read the posts</strong>
      <span>What To Do reads posts with your Claude subscription. Nothing was read this time.</span>
      {status?.error && <span className="claude-sign-in__error">{status.error}</span>}
      <button type="button" className="button button--small claude-sign-in__action" onClick={signIn.start} disabled={signIn.starting}>
        Sign in to Claude
      </button>
    </div>
  );
}

function CodeFallback({
  pageUrl,
  onSubmit,
  submitting,
  error,
  cliError,
}: {
  pageUrl: string;
  onSubmit: (code: string) => void;
  submitting: boolean;
  error: unknown;
  cliError: string | null;
}) {
  const [code, setCode] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (code.trim()) onSubmit(code.trim());
  };
  return (
    <details className="claude-sign-in__fallback" open={cliError ? true : undefined}>
      <summary>The browser didn’t open?</summary>
      <ol className="claude-sign-in__steps">
        <li>
          <a href={pageUrl} target="_blank" rel="noreferrer">
            Open the sign-in page
          </a>
        </li>
        <li>Sign in, then copy the code the page shows.</li>
        <li>
          <form className="claude-sign-in__code" onSubmit={submit}>
            <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Paste the code" aria-label="Code from the sign-in page" />
            <button type="submit" className="button button--small" disabled={submitting || !code.trim()}>
              Sign in
            </button>
          </form>
        </li>
      </ol>
      {error != null && <span className="claude-sign-in__error">{errorText(error)}</span>}
      {error == null && cliError && <span className="claude-sign-in__error">{cliError}</span>}
    </details>
  );
}
