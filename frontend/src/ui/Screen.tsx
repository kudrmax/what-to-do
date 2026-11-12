import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { errorText } from "./errors";
import "./Screen.css";

export function Screen({ title, action, toolbar, children, narrow }: { title: string; action?: ReactNode; toolbar?: ReactNode; children: ReactNode; narrow?: boolean }) {
  return (
    <div className={`screen${narrow ? " screen--narrow" : ""}`}>
      <header className="screen__header">
        <div className="screen__title-row">
          <h1 className="title">{title}</h1>
          {action}
        </div>
        {toolbar}
      </header>
      {children}
    </div>
  );
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="screen-section">
      <div className="screen-section__head">
        <h2 className="section-title">{title}</h2>
        {hint && <p className="screen-section__hint">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export function EmptyState({ title, text, link, action }: { title: string; text?: string; link?: { to: string; label: string }; action?: { label: string; onClick: () => void } }) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {text && <p className="empty__text">{text}</p>}
      {link && (
        <Link to={link.to} className="button button--small">
          {link.label}
        </Link>
      )}
      {action && (
        <button type="button" className="button button--small" onClick={action.onClick}>
          {action.label}
        </button>
      )}
    </div>
  );
}

/** A list the backend could not give: says so and why, instead of an empty page. */
export function LoadError({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return <EmptyState title="Не получилось загрузить" text={errorText(error) ?? undefined} action={onRetry && { label: "Попробовать ещё раз", onClick: onRetry }} />;
}
