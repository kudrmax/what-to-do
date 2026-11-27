import type { ReactNode } from "react";

import type { CityStats, Plan } from "../api/client";
import { useStats } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { useReader } from "../api/useReader";
import { SECTIONS } from "../app/routes";
import { dayAndMonth, plural } from "../domain/dates";
import { PLANS } from "../domain/plans";
import { BarList, ColumnChart, PartsBar, StatTile, type Part } from "../stats/charts";
import { formatNumber, formatShare } from "../stats/format";
import { Icon } from "../ui/Icon";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";
import "./StatsScreen.css";

const PLAN_COLORS: Record<Plan, string> = { sure: "var(--plan-sure)", maybe: "var(--plan-maybe)", went: "var(--plan-went)", no: "var(--plan-no)" };
const PLAN_ORDER: Plan[] = ["sure", "maybe", "went", "no"];
const GOING: Plan[] = ["maybe", "sure", "went"];
const UNMARKED_COLOR = "var(--line-strong)";

const cards = (count: number) => `${formatNumber(count)} ${plural(count, "card", "cards")}`;

/** Counts of everything the app read and found in the active city, and of how the user marked it. */
export function StatsScreen() {
  const { city } = useActiveCity();
  const stats = useStats(city !== null);
  const reader = useReader();
  return (
    <Screen title={SECTIONS.stats.title}>
      {!city ? (
        <NoCity />
      ) : stats.isError ? (
        <LoadError error={stats.error} />
      ) : stats.data?.posts.read === 0 ? (
        <EmptyState title="Nothing to count yet" text={`Stats will appear after the first refresh, once ${reader.name} has read the channels’ posts and the websites’ pages.`} />
      ) : (
        stats.data && <Dashboard stats={stats.data} />
      )}
    </Screen>
  );
}

function Dashboard({ stats }: { stats: CityStats }) {
  return (
    <div className="stats">
      <div className="stats__tiles">
        <StatTile icon="text" label="Posts and pages read" value={stats.posts.read} note={`${formatNumber(stats.posts.with_events)} of them have events`} />
        <StatTile icon="image" label="Photos read" value={stats.photos.read} note={`${formatNumber(stats.photos.with_text)} with text`} />
        <StatTile icon="calendar" label="Events found" value={stats.events.cards} note={`${cards(stats.events.merged)} from several sources`} />
        <StatTile icon="bookmark" label="Marked" value={stats.marked} note={`${formatShare(stats.marked, stats.events.cards)} of all cards`} />
      </div>

      <Panel title="From announcement to plans" hint="A post or website page can announce several events, and one event can come from several sources. Such announcements are merged into one card.">
        <BarList label="From announcement to plans" rows={pipeline(stats)} />
      </Panel>

      <div className="stats__pair">
        <Panel title="Statuses">
          <PartsBar label="Card statuses" parts={planParts(stats)} />
        </Panel>
        <Panel title="Interest">
          <InterestChart stats={stats} />
        </Panel>
      </div>

      <Panel title="Posts and pages by week" hint="How many of the posts and website pages read appeared each week, and how many of them had events.">
        <ColumnChart
          label="Posts and pages by week"
          series={[
            { label: "With events", className: "series-accent" },
            { label: "Without events", className: "series-rest" },
          ]}
          columns={stats.weeks.map((week) => ({
            key: week.start,
            label: dayAndMonth(week.start),
            values: [week.posts_with_events, week.posts - week.posts_with_events],
            tip: `Week of ${dayAndMonth(week.start)}: ${formatNumber(week.posts)} read, ${formatNumber(week.posts_with_events)} with events`,
          }))}
        />
      </Panel>

      <div className="stats__pair">
        <Panel title="Tags">
          <BarList label="Cards by tag" rows={stats.tags.map((t) => ({ key: t.tag, label: t.tag, value: t.count, tip: `${t.tag}: ${cards(t.count)}` }))} />
        </Panel>
        <Panel title="Sources">
          <SourceTable stats={stats} />
        </Panel>
      </div>
    </div>
  );
}

function Panel({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="stats-panel">
      <div className="stats-panel__head">
        <h2 className="section-title">{title}</h2>
        {hint && <p className="stats-panel__hint">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function pipeline(stats: CityStats) {
  const going = stats.plans.filter((p) => p.plan && GOING.includes(p.plan)).reduce((sum, p) => sum + p.count, 0);
  return [
    { key: "posts", label: "Posts and pages read", value: stats.posts.read, tip: `${formatNumber(stats.posts.read)} read in all` },
    { key: "announcements", label: "Announcements in them", value: stats.events.announcements, tip: "Each event in each post and on each page counted separately" },
    { key: "cards", label: "Cards after merging", value: stats.events.cards, tip: `Duplicates merged: ${formatNumber(stats.events.announcements - stats.events.cards)}` },
    { key: "marked", label: "Marked by you", value: stats.marked, tip: "With an interest or a status" },
    { key: "going", label: "Planned to go", value: going, tip: "Maybe going, going for sure and went" },
  ];
}

function planParts(stats: CityStats): Part[] {
  const count = (plan: Plan | null) => stats.plans.find((p) => (p.plan ?? null) === plan)?.count ?? 0;
  return [
    ...PLAN_ORDER.map((plan) => ({ key: plan, label: PLANS[plan].label, value: count(plan), color: PLAN_COLORS[plan], icon: PLANS[plan].icon })),
    { key: "none", label: "No status", value: count(null), color: UNMARKED_COLOR },
  ];
}

function InterestChart({ stats }: { stats: CityStats }) {
  const rated = stats.interests.filter((i) => i.interest !== null).reverse();
  const unrated = stats.interests.find((i) => i.interest === null)?.count ?? 0;
  return (
    <div className="interest">
      <ColumnChart
        label="Cards by interest"
        height={150}
        series={[{ label: "Cards", className: "series-accent" }]}
        columns={rated.map((i) => ({
          key: String(i.interest),
          label: (
            <span className="interest__tick">
              <Icon name="star" size={12} />
              {i.interest}
            </span>
          ),
          values: [i.count],
          tip: `${i.interest} of 5: ${cards(i.count)}`,
        }))}
      />
      <p className="interest__note">Not rated: {cards(unrated)}</p>
    </div>
  );
}

function SourceTable({ stats }: { stats: CityStats }) {
  const maxPosts = Math.max(1, ...stats.sources.map((s) => s.posts));
  const maxEvents = Math.max(1, ...stats.sources.map((s) => s.events));
  return (
    <table className="source-stats">
      <thead>
        <tr>
          <th>Source</th>
          <th>Read</th>
          <th>Events</th>
        </tr>
      </thead>
      <tbody>
        {stats.sources.map((source) => (
          <tr key={source.id}>
            <td className="source-stats__name">{source.title}</td>
            <td>
              <MiniBar value={source.posts} max={maxPosts} tip={`${source.title}: ${formatNumber(source.posts)} read`} quiet />
            </td>
            <td>
              <MiniBar value={source.events} max={maxEvents} tip={`${source.title}: ${cards(source.events)}`} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MiniBar({ value, max, tip, quiet }: { value: number; max: number; tip: string; quiet?: boolean }) {
  return (
    <span className="mini-bar" data-tip={tip} tabIndex={0}>
      <span className="mini-bar__value">{formatNumber(value)}</span>
      <span className="mini-bar__track">
        <span className={`mini-bar__fill${quiet ? " mini-bar__fill--quiet" : ""}`} style={{ width: `${(value / max) * 100}%` }} />
      </span>
    </span>
  );
}
