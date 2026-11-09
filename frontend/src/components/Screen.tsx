import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import "./Screen.css";

export function Screen({ title, action, filters, children, narrow }: { title: string; action?: ReactNode; filters?: ReactNode; children: ReactNode; narrow?: boolean }) {
  return (
    <div className={`screen${narrow ? " screen--narrow" : ""}`}>
      <header className="screen__header">
        <div className="screen__title-row">
          <h1>{title}</h1>
          {action}
        </div>
        {filters}
      </header>
      {children}
    </div>
  );
}

export function EmptyState({ title, text, link }: { title: string; text?: string; link?: { to: string; label: string } }) {
  return (
    <div className="empty">
      <p className="empty__title">{title}</p>
      {text && <p className="empty__text">{text}</p>}
      {link && (
        <Link to={link.to} className="empty__link">
          {link.label}
        </Link>
      )}
    </div>
  );
}
