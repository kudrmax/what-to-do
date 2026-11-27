import { useState, type FormEvent } from "react";

import type { LlmProvider, ReaderSignIn as SignInView } from "../api/client";
import { useReaderSignIn } from "../api/queries";
import { READERS, type Reader } from "../domain/readers";
import { CommandLine } from "../ui/CommandLine";
import { Icon } from "../ui/Icon";
import { errorText } from "../ui/errors";

/** Shown under Refresh when the reader can't read: says how to install or update it, why it is refused, or signs in through the browser. */
export function ReaderSignIn({ provider }: { provider: LlmProvider }) {
  const signIn = useReaderSignIn(provider);
  const status = signIn.status;
  const reader = READERS[provider];

  if (!status) return null;

  if (status.state === "signed_in") {
    return (
      <div className="note reader-sign-in reader-sign-in--done" role="status">
        <strong className="reader-sign-in__title">
          <Icon name="check" size={16} strokeWidth={2.4} />
          Signed in to {reader.account}
        </strong>
        <span>Press Refresh to read the posts.</span>
      </div>
    );
  }

  if (status.state === "not_installed") return <Install reader={reader} />;
  if (status.state === "too_old") return <Update reader={reader} status={status} />;
  if (status.state === "refused") return <Refused reader={reader} status={status} />;

  if (status.signing_in) {
    return (
      <div className="note reader-sign-in" role="status">
        <strong className="reader-sign-in__title">
          <span className="spinner" />
          Finish signing in in your browser
        </strong>
        <span>Come back here once the page says you’re signed in.</span>
        {status.page_url &&
          (provider === "claude" ? (
            <CodeFallback pageUrl={status.page_url} onSubmit={signIn.submitCode} submitting={signIn.submitting} error={signIn.codeError} cliError={status.error ?? null} />
          ) : (
            <PageFallback pageUrl={status.page_url} error={status.error ?? null} />
          ))}
      </div>
    );
  }

  return (
    <div className="note reader-sign-in" role="alert">
      <strong className="reader-sign-in__title">Sign in to {reader.account} to read the posts</strong>
      <span>What To Do reads posts with {reader.plan}. Nothing was read this time.</span>
      {status.error && <span className="reader-sign-in__error">{status.error}</span>}
      <button type="button" className="button button--small reader-sign-in__action" onClick={signIn.start} disabled={signIn.starting}>
        Sign in to {reader.account}
      </button>
    </div>
  );
}

function Install({ reader }: { reader: Reader }) {
  return (
    <div className="note reader-sign-in" role="alert">
      <strong className="reader-sign-in__title">Install {reader.program} to read the posts</strong>
      <span>
        What To Do reads posts with {reader.plan} through {reader.program}. Paste one of these into a terminal:
      </span>
      {reader.install.map(({ label, command }) => (
        <div key={label} className="reader-sign-in__command">
          <span className="reader-sign-in__command-label">{label}</span>
          <CommandLine command={command} />
        </div>
      ))}
      <span>Then press Refresh.</span>
    </div>
  );
}

function Update({ reader, status }: { reader: Reader; status: SignInView }) {
  return (
    <div className="note reader-sign-in" role="alert">
      <strong className="reader-sign-in__title">Update {reader.program} to read the posts</strong>
      <span>
        You have {status.version ?? "an older version"}. What To Do needs {status.minimum} or newer.
      </span>
      {status.update_command ? (
        <>
          <span>Paste this into a terminal:</span>
          <CommandLine command={status.update_command} />
        </>
      ) : (
        <span>Update it the way you installed it.</span>
      )}
      <span>Then press Refresh.</span>
    </div>
  );
}

function Refused({ reader, status }: { reader: Reader; status: SignInView }) {
  const message = "message" in status ? status.message : null;
  return (
    <div className="note reader-sign-in" role="alert">
      <strong className="reader-sign-in__title">{reader.program} can’t be used safely</strong>
      {message && <span>{message}</span>}
      <span>No post was sent to it.</span>
    </div>
  );
}

function PageFallback({ pageUrl, error }: { pageUrl: string; error: string | null }) {
  return (
    <details className="reader-sign-in__fallback" open={error ? true : undefined}>
      <summary>The browser didn’t open?</summary>
      <ol className="reader-sign-in__steps">
        <li>
          <a href={pageUrl} target="_blank" rel="noreferrer">
            Open the sign-in page
          </a>
        </li>
        <li>Sign in. This box changes by itself once you’re done.</li>
      </ol>
      {error && <span className="reader-sign-in__error">{error}</span>}
    </details>
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
    <details className="reader-sign-in__fallback" open={cliError ? true : undefined}>
      <summary>The browser didn’t open?</summary>
      <ol className="reader-sign-in__steps">
        <li>
          <a href={pageUrl} target="_blank" rel="noreferrer">
            Open the sign-in page
          </a>
        </li>
        <li>Sign in, then copy the code the page shows.</li>
        <li>
          <form className="reader-sign-in__code" onSubmit={submit}>
            <input className="input" value={code} onChange={(event) => setCode(event.target.value)} placeholder="Paste the code" aria-label="Code from the sign-in page" />
            <button type="submit" className="button button--small" disabled={submitting || !code.trim()}>
              Sign in
            </button>
          </form>
        </li>
      </ol>
      {error != null && <span className="reader-sign-in__error">{errorText(error)}</span>}
      {error == null && cliError && <span className="reader-sign-in__error">{cliError}</span>}
    </details>
  );
}
