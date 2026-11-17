import { useEffect, useId, useMemo, useState, type FormEvent, type ReactNode } from "react";
import qrcode from "qrcode-generator";

import type { PhonePage } from "../api/client";
import { usePhonePage, usePublishPhonePage, useTurnPhonePageOff, useTurnPhonePageOn } from "../api/queries";
import { ago } from "../domain/dates";
import { errorText } from "../ui/errors";
import { Icon } from "../ui/Icon";
import { IconButton } from "../ui/IconButton";
import { Section } from "../ui/Screen";
import "./PhonePageSection.css";

const NEW_REPOSITORY_URL = "https://github.com/new";
const NEW_TOKEN_URL = "https://github.com/settings/personal-access-tokens/new";
const TOKEN_PERMISSIONS = ["Contents", "Pages"];
const PAGES_GUIDE_URL = "https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site";
const PAGES_SETTINGS = [
  { name: "Source", value: "Deploy from a branch" },
  { name: "Branch", value: "main" },
  { name: "Folder", value: "/ (root)" },
];
const REPOSITORY = /^[A-Za-z0-9-]+\/[A-Za-z0-9._-]+$/;
const PAGES_OFF = "Turn on GitHub Pages for this repository: Settings → Pages → Deploy from a branch, main, / (root). Then turn the page on again.";

type Field = "repository" | "token" | "password";

const FIELD_OF_ERROR: Record<string, Field> = {
  "Repository not found": "repository",
  "The repository must look like owner/name": "repository",
  "This repository already has other files. Create a new empty one.": "repository",
  "The token has no access to this repository": "token",
  "The token expired or was revoked": "token",
  "Enter the token": "token",
  "Enter the password": "password",
};

export function PhonePageSection() {
  const state = usePhonePage();
  const publish = usePublishPhonePage();
  const turnOff = useTurnPhonePageOff();
  const page = state.data;
  const enabled = page?.enabled;
  const forgetTurnOffError = turnOff.reset;
  useEffect(() => {
    if (enabled) forgetTurnOffError();
  }, [enabled, forgetTurnOffError]);
  return (
    <Section title="Phone page" hint="Your upcoming plans on a web page for the phone, locked with a password. The app keeps it on GitHub Pages and updates it while it runs.">
      {page?.enabled && <Published page={page} busy={publish.isPending || turnOff.isPending} onPublish={() => publish.mutate()} onTurnOff={() => turnOff.mutate()} error={publish.error ?? turnOff.error} />}
      {page && !page.enabled && turnOff.error ? <LeftBehind error={turnOff.error} /> : null}
      {page && <ConnectionForm key={String(page.enabled)} page={page} />}
      {state.isError && <p className="error-text">{errorText(state.error)}</p>}
    </Section>
  );
}

/** Turning off failed on GitHub's side: the app stopped publishing, but the last plans are still there. */
function LeftBehind({ error }: { error: unknown }) {
  return (
    <div className="phone-page__left-behind" role="alert">
      <Icon name="alert" size={16} className="phone-page__left-behind-icon" />
      <div className="phone-page__left-behind-text">
        <p>The page is off, but GitHub still has the last published plans, encrypted. Turn it on and off again to clear them.</p>
        <p className="error-text">{errorText(error)}</p>
      </div>
    </div>
  );
}

function Guide({ repository }: { repository: string }) {
  return (
    <ol className="phone-guide" aria-label="How to set it up">
      <li className="phone-guide__step">
        <p className="phone-guide__text">
          Create an empty public repository with any name, for example <code className="phone-guide__code">what-to-do-plans</code>
        </p>
        <ExternalLink href={NEW_REPOSITORY_URL}>New repository on GitHub</ExternalLink>
      </li>
      <li className="phone-guide__step">
        <p className="phone-guide__text">Create a fine-grained token for only that repository, with these permissions</p>
        <ul className="phone-guide__permissions" aria-label="Token permissions">
          {TOKEN_PERMISSIONS.map((name) => (
            <li key={name} className="phone-guide__permission">
              <span className="phone-guide__permission-name">{name}</span>
              <span className="phone-guide__permission-access">Read and write</span>
            </li>
          ))}
        </ul>
        <ExternalLink href={NEW_TOKEN_URL}>New token on GitHub</ExternalLink>
      </li>
      <li className="phone-guide__step">
        <p className="phone-guide__text">Fill in the fields below and press Turn on. The password is what you type on the phone to open it.</p>
      </li>
      <li className="phone-guide__step">
        <p className="phone-guide__text">If the app says GitHub Pages is off, turn it on in the repository’s settings and press Turn on again</p>
        <PagesSettings repository={repository} />
      </li>
    </ol>
  );
}

/** What to choose in the repository's Pages settings, and a link straight there once the repository is known. */
function PagesSettings({ repository }: { repository: string }) {
  const known = REPOSITORY.test(repository);
  return (
    <>
      <ul className="phone-guide__permissions" aria-label="GitHub Pages settings">
        {PAGES_SETTINGS.map(({ name, value }) => (
          <li key={name} className="phone-guide__permission">
            <span className="phone-guide__permission-name">{name}</span>
            <span className="phone-guide__permission-access phone-guide__permission-access--setting">{value}</span>
          </li>
        ))}
      </ul>
      <ExternalLink href={known ? `https://github.com/${repository}/settings/pages` : PAGES_GUIDE_URL}>{known ? "Pages settings on GitHub" : "How to turn on GitHub Pages"}</ExternalLink>
    </>
  );
}

/** The plans are uploaded, but the token may not turn Pages on: the user does it once on GitHub. */
function PagesOff({ repository }: { repository: string }) {
  return (
    <div className="phone-form__pages-off" role="alert">
      <Icon name="alert" size={16} className="phone-form__pages-off-icon" />
      <div className="phone-form__pages-off-text">
        <p className="phone-form__pages-off-title">GitHub Pages is off for this repository</p>
        <p>The plans are uploaded. Turn Pages on in the repository’s settings, then press Turn on again.</p>
        <PagesSettings repository={repository} />
      </div>
    </div>
  );
}

function ExternalLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a className="phone-guide__link" href={href} target="_blank" rel="noreferrer">
      {children}
      <Icon name="external" size={14} />
    </a>
  );
}

interface PublishedProps {
  page: PhonePage;
  busy: boolean;
  error: unknown;
  onPublish: () => void;
  onTurnOff: () => void;
}

function Published({ page, busy, error, onPublish, onTurnOff }: PublishedProps) {
  return (
    <div className="phone-page">
      {page.page_url && <QrCode text={page.page_url} />}
      <div className="phone-page__details">
        {page.page_url && <PageLink url={page.page_url} />}
        <PublishState page={page} />
        <div className="phone-page__actions">
          <button type="button" className="button button--small" disabled={busy || page.publishing} onClick={onPublish}>
            Publish now
          </button>
          <button type="button" className="button button--quiet button--small" disabled={busy} onClick={onTurnOff}>
            Turn off
          </button>
        </div>
        {error ? <p className="error-text">{errorText(error)}</p> : null}
      </div>
    </div>
  );
}

const COPY_LABELS = { idle: "Copy", copied: "Copied", failed: "Couldn’t copy" } as const;

function PageLink({ url }: { url: string }) {
  const [copy, setCopy] = useState<keyof typeof COPY_LABELS>("idle");
  const copyLink = () => {
    if (!navigator.clipboard) return setCopy("failed");
    navigator.clipboard.writeText(url).then(
      () => setCopy("copied"),
      () => setCopy("failed"),
    );
  };
  return (
    <div className="phone-page__link-row">
      <Icon name="link" size={16} className="phone-page__link-icon" />
      <a className="phone-page__link" href={url} target="_blank" rel="noreferrer">
        {url}
      </a>
      <button type="button" className="button button--quiet button--small" onClick={copyLink}>
        {COPY_LABELS[copy]}
      </button>
    </div>
  );
}

function PublishState({ page }: { page: PhonePage }) {
  if (page.publishing) {
    return (
      <p className="phone-page__state phone-page__state--busy">
        <Icon name="refresh" size={15} className="phone-page__spinner" />
        <span>Publishing…</span>
      </p>
    );
  }
  if (page.last_error) {
    return (
      <p className="phone-page__state phone-page__state--failed error-text">
        <Icon name="alert" size={15} />
        <span>{page.last_error}</span>
      </p>
    );
  }
  if (!page.published_at) return null;
  return (
    <p className="phone-page__state">
      <Icon name="check" size={15} className="phone-page__ok" />
      <span>Published {ago(page.published_at)}</span>
    </p>
  );
}

/** Black on white whatever the theme: phone cameras read that best. */
function QrCode({ text }: { text: string }) {
  const { size, path } = useMemo(() => {
    const code = qrcode(0, "M");
    code.addData(text);
    code.make();
    const count = code.getModuleCount();
    let d = "";
    for (let row = 0; row < count; row++) {
      for (let column = 0; column < count; column++) {
        if (code.isDark(row, column)) d += `M${column} ${row}h1v1h-1z`;
      }
    }
    return { size: count, path: d };
  }, [text]);
  const quiet = 4;
  return (
    <svg className="phone-page__qr" role="img" aria-label="QR code of the page link" viewBox={`${-quiet} ${-quiet} ${size + 2 * quiet} ${size + 2 * quiet}`} shapeRendering="crispEdges">
      <rect x={-quiet} y={-quiet} width={size + 2 * quiet} height={size + 2 * quiet} fill="#ffffff" />
      <path d={path} fill="#000000" />
    </svg>
  );
}

function ConnectionForm({ page }: { page: PhonePage }) {
  const turnOn = useTurnPhonePageOn();
  const ids = useId();
  const [repository, setRepository] = useState(page.repository);
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const message = errorText(turnOn.error);
  const field = message ? FIELD_OF_ERROR[message] : undefined;
  const errorOf = (name: Field) => (field === name ? message : null);
  const pagesOff = message === PAGES_OFF;
  const formError = message && !field && !pagesOff ? message : null;
  const changed = repository.trim() !== page.repository || token !== "" || password !== "";
  const edit = (set: (value: string) => void) => (value: string) => {
    set(value);
    if (turnOn.error) turnOn.reset();
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    turnOn.mutate(
      { repository: repository.trim(), token: token || null, password: password || null },
      {
        onSuccess: () => {
          setToken("");
          setPassword("");
        },
      },
    );
  };
  return (
    <>
      {!page.enabled && <Guide repository={repository.trim()} />}
      <form className="phone-form" onSubmit={submit}>
        <div className="phone-form__fields">
          <FormField id={`${ids}-repository`} label="Repository" error={errorOf("repository")}>
            <input
              id={`${ids}-repository`}
              className="input"
              value={repository}
              placeholder="owner/name"
              spellCheck={false}
              autoComplete="off"
              aria-invalid={field === "repository"}
              aria-describedby={describedBy(`${ids}-repository`, field === "repository")}
              onChange={(e) => edit(setRepository)(e.target.value)}
            />
          </FormField>
          <FormField id={`${ids}-token`} label="Token" error={errorOf("token")}>
            <input
              id={`${ids}-token`}
              className="input"
              type="password"
              value={token}
              placeholder={page.has_token ? "Saved" : "github_pat_…"}
              autoComplete="off"
              aria-invalid={field === "token"}
              aria-describedby={describedBy(`${ids}-token`, field === "token")}
              onChange={(e) => edit(setToken)(e.target.value)}
            />
          </FormField>
          <FormField id={`${ids}-password`} label="Password" error={errorOf("password")} hint="Typed on the phone to open the page">
            <div className="phone-form__secret">
              <input
                id={`${ids}-password`}
                className="input phone-form__secret-input"
                type={showPassword ? "text" : "password"}
                value={password}
                placeholder={page.has_password ? "Saved" : undefined}
                autoComplete="new-password"
                aria-invalid={field === "password"}
                aria-describedby={describedBy(`${ids}-password`, field === "password", true)}
                onChange={(e) => edit(setPassword)(e.target.value)}
              />
              <IconButton
                icon={showPassword ? "eyeOff" : "eye"}
                label={showPassword ? "Hide the password" : "Show the password"}
                aria-pressed={showPassword}
                className="phone-form__eye"
                onClick={() => setShowPassword(!showPassword)}
              />
            </div>
          </FormField>
        </div>
        <div className="phone-form__actions">
          {page.enabled ? (
            <button type="submit" className="button button--small" disabled={!changed || turnOn.isPending}>
              {turnOn.isPending ? "Saving…" : "Save and publish"}
            </button>
          ) : (
            <button type="submit" className="button" disabled={turnOn.isPending}>
              {turnOn.isPending ? "Turning on…" : "Turn on"}
            </button>
          )}
          {formError && <p className="error-text phone-form__error">{formError}</p>}
        </div>
        {pagesOff && <PagesOff repository={turnOn.variables?.repository ?? repository.trim()} />}
      </form>
    </>
  );
}

function describedBy(id: string, hasError: boolean, hasHint = false): string | undefined {
  const ids = [hasError && `${id}-error`, hasHint && `${id}-hint`].filter(Boolean);
  return ids.length ? ids.join(" ") : undefined;
}

function FormField({ id, label, error, hint, children }: { id: string; label: string; error: string | null; hint?: string; children: ReactNode }) {
  return (
    <div className="phone-form__field">
      <label className="label" htmlFor={id}>
        {label}
      </label>
      {children}
      {error && (
        <span id={`${id}-error`} className="error-text">
          {error}
        </span>
      )}
      {hint && (
        <span id={`${id}-hint`} className="phone-form__hint">
          {hint}
        </span>
      )}
    </div>
  );
}
