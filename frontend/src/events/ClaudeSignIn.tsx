import { useState, type FormEvent } from "react";

import type { ClaudeSignIn as SignInView } from "../api/client";
import { useClaudeSignIn } from "../api/queries";
import { CommandLine } from "../ui/CommandLine";
import { Icon } from "../ui/Icon";
import { errorText } from "../ui/errors";

const INSTALL_COMMANDS = [
  { label: "Installer", command: "curl -fsSL https://claude.ai/install.sh | bash" },
  { label: "Homebrew", command: "brew install --cask claude-code@latest" },
];

/** Shown under Refresh when Claude Code can't read: says how to install or update it, or signs in through the browser. */
export function ClaudeSignIn() {
  const signIn = useClaudeSignIn();
  const status = signIn.status;

  if (!status) return null;

  if (status.state === "signed_in") {
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

  if (status.state === "not_installed") return <InstallClaudeCode />;
  if (status.state === "too_old") return <UpdateClaudeCode status={status} />;

  if (status.signing_in) {
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
      {status.error && <span className="claude-sign-in__error">{status.error}</span>}
      <button type="button" className="button button--small claude-sign-in__action" onClick={signIn.start} disabled={signIn.starting}>
        Sign in to Claude
      </button>
    </div>
  );
}

function InstallClaudeCode() {
  return (
    <div className="note claude-sign-in" role="alert">
      <strong className="claude-sign-in__title">Install Claude Code to read the posts</strong>
      <span>What To Do reads posts with your Claude subscription through Claude Code. Paste one of these into a terminal:</span>
      {INSTALL_COMMANDS.map(({ label, command }) => (
        <div key={label} className="claude-sign-in__command">
          <span className="claude-sign-in__command-label">{label}</span>
          <CommandLine command={command} />
        </div>
      ))}
      <span>Then press Refresh.</span>
    </div>
  );
}

function UpdateClaudeCode({ status }: { status: SignInView }) {
  return (
    <div className="note claude-sign-in" role="alert">
      <strong className="claude-sign-in__title">Update Claude Code to read the posts</strong>
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
