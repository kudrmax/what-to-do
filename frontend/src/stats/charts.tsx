import type { ReactNode } from "react";

import { Icon, type IconName } from "../ui/Icon";
import { formatNumber, formatShare } from "./format";
import "./charts.css";


const width = (value: number, max: number) => `${max ? (value / max) * 100 : 0}%`;

export function StatTile({ icon, label, value, note }: { icon: IconName; label: string; value: number; note?: ReactNode }) {
  return (
    <div className="stat-tile">
      <span className="stat-tile__label">
        <Icon name={icon} size={16} />
        {label}
      </span>
      <span className="stat-tile__value">{formatNumber(value)}</span>
      {note && <span className="stat-tile__note">{note}</span>}
    </div>
  );
}

export interface BarRow {
  key: string;
  label: ReactNode;
  value: number;
  tip: string;
}

/** Ranked horizontal bars of one measure: a label, a bar and its value on each row. */
export function BarList({ rows, label }: { rows: BarRow[]; label: string }) {
  const max = Math.max(0, ...rows.map((row) => row.value));
  return (
    <ul className="bar-list" aria-label={label}>
      {rows.map((row) => (
        <li key={row.key} className="bar-list__row">
          <span className="bar-list__label">{row.label}</span>
          <span className="bar-list__track">
            <span className="bar-list__bar" style={{ width: width(row.value, max) }} data-tip={row.tip} tabIndex={0} />
          </span>
          <span className="bar-list__value">{formatNumber(row.value)}</span>
        </li>
      ))}
    </ul>
  );
}

export interface Part {
  key: string;
  label: string;
  value: number;
  color: string;
  icon?: IconName;
}

/** Parts of a whole as one bar, with a legend that gives every part its count and share. */
export function PartsBar({ parts, label }: { parts: Part[]; label: string }) {
  const total = parts.reduce((sum, part) => sum + part.value, 0);
  return (
    <div className="parts">
      <div className="parts__bar" role="img" aria-label={label}>
        {parts
          .filter((part) => part.value > 0)
          .map((part) => (
            <span
              key={part.key}
              className="parts__segment"
              style={{ flexGrow: part.value, background: part.color }}
              data-tip={`${part.label}: ${formatNumber(part.value)}`}
              tabIndex={0}
            />
          ))}
      </div>
      <ul className="parts__legend">
        {parts.map((part) => (
          <li key={part.key} className="parts__item">
            <span className="parts__swatch" style={{ background: part.color }}>
              {part.icon && <Icon name={part.icon} size={12} strokeWidth={2.6} />}
            </span>
            <span className="parts__name">{part.label}</span>
            <span className="parts__count">{formatNumber(part.value)}</span>
            <span className="parts__share">{formatShare(part.value, total)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export interface Column {
  key: string;
  label: ReactNode;
  /** Bottom first; each value is drawn in the series of the same index. */
  values: number[];
  tip: string;
}

export interface Series {
  label: string;
  className: string;
}

/** Vertical columns, stacked when there are several series; a legend names the series. */
export function ColumnChart({ columns, series, label, height = 160 }: { columns: Column[]; series: Series[]; label: string; height?: number }) {
  const max = Math.max(1, ...columns.map((column) => column.values.reduce((a, b) => a + b, 0)));
  return (
    <div className="columns">
      {series.length > 1 && (
        <ul className="columns__legend">
          {series.map((s) => (
            <li key={s.label}>
              <span className={`columns__swatch ${s.className}`} />
              {s.label}
            </li>
          ))}
        </ul>
      )}
      <div className="columns__plot" role="img" aria-label={label} style={{ height }}>
        {columns.map((column) => (
          <div key={column.key} className="columns__column" data-tip={column.tip} tabIndex={0}>
            <div className="columns__stack" style={{ height: width(column.values.reduce((a, b) => a + b, 0), max) }}>
              {column.values.map((value, index) =>
                value > 0 ? <span key={index} className={`columns__part ${series[index].className}`} style={{ flexGrow: value }} /> : null,
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="columns__axis">
        {columns.map((column) => (
          <span key={column.key} className="columns__tick">
            {column.label}
          </span>
        ))}
      </div>
    </div>
  );
}
