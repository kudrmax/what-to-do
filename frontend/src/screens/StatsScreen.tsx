import type { ReactNode } from "react";

import type { CityStats, Plan } from "../api/client";
import { useStats } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { SECTIONS } from "../app/routes";
import { dayAndMonth, plural } from "../domain/dates";
import { PLANS } from "../domain/plans";
import { BarList, ColumnChart, PartsBar, StatTile, type Part } from "../stats/charts";
import { formatNumber, formatShare } from "../stats/format";
import { Icon } from "../ui/Icon";
import { EmptyState, LoadError, Screen } from "../ui/Screen";
import { NoCity } from "./NoCity";
import "./StatsScreen.css";

const PLAN_COLORS: Record<Plan, string> = { sure: "#dc4c3e", maybe: "#eda100", went: "#1baf7a", no: "#2a78d6" };
const PLAN_ORDER: Plan[] = ["sure", "maybe", "went", "no"];
const GOING: Plan[] = ["maybe", "sure", "went"];
const UNMARKED_COLOR = "var(--line-strong)";

const cards = (count: number) => `${formatNumber(count)} ${plural(count, "карточка", "карточки", "карточек")}`;
const posts = (count: number) => `${formatNumber(count)} ${plural(count, "пост", "поста", "постов")}`;

/** Counts of everything the app read and found in the active city, and of how the user marked it. */
export function StatsScreen() {
  const { city } = useActiveCity();
  const stats = useStats(city !== null);
  return (
    <Screen title={SECTIONS.stats.title}>
      {!city ? (
        <NoCity />
      ) : stats.isError ? (
        <LoadError error={stats.error} />
      ) : stats.data?.posts.read === 0 ? (
        <EmptyState title="Пока нечего считать" text="Статистика появится после первого обновления: когда Claude прочитает посты каналов." />
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
        <StatTile icon="text" label="Постов прочитано" value={stats.posts.read} note={`в ${formatNumber(stats.posts.with_events)} ${plural(stats.posts.with_events, "посте", "постах", "постах")} есть события`} />
        <StatTile icon="image" label="Фото прочитано" value={stats.photos.read} note={`текст есть на ${formatNumber(stats.photos.with_text)}`} />
        <StatTile icon="calendar" label="Событий найдено" value={stats.events.cards} note={`${cards(stats.events.merged)} из нескольких постов`} />
        <StatTile icon="bookmark" label="Отмечено" value={stats.marked} note={`${formatShare(stats.marked, stats.events.cards)} всех карточек`} />
      </div>

      <Panel title="От поста до планов" hint="Пост может анонсировать несколько событий, а одно событие — прийти из нескольких постов: такие анонсы склеиваются в одну карточку.">
        <BarList label="От поста до планов" rows={pipeline(stats)} />
      </Panel>

      <div className="stats__pair">
        <Panel title="Статусы">
          <PartsBar label="Статусы карточек" parts={planParts(stats)} />
        </Panel>
        <Panel title="Интерес">
          <InterestChart stats={stats} />
        </Panel>
      </div>

      <Panel title="Посты по неделям" hint="Сколько прочитанных постов опубликовано за неделю и в скольких из них нашлись события.">
        <ColumnChart
          label="Посты по неделям"
          series={[
            { label: "С событиями", className: "series-accent" },
            { label: "Без событий", className: "series-rest" },
          ]}
          columns={stats.weeks.map((week) => ({
            key: week.start,
            label: dayAndMonth(week.start),
            values: [week.posts_with_events, week.posts - week.posts_with_events],
            tip: `Неделя с ${dayAndMonth(week.start)}: ${posts(week.posts)}, с событиями ${formatNumber(week.posts_with_events)}`,
          }))}
        />
      </Panel>

      <div className="stats__pair">
        <Panel title="Теги">
          <BarList label="Карточки по тегам" rows={stats.tags.map((t) => ({ key: t.tag, label: t.tag, value: t.count, tip: `${t.tag}: ${cards(t.count)}` }))} />
        </Panel>
        <Panel title="Источники">
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
    { key: "posts", label: "Постов прочитано", value: stats.posts.read, tip: `Claude прочитал ${posts(stats.posts.read)}` },
    { key: "announcements", label: "Анонсов в постах", value: stats.events.announcements, tip: "Каждое событие в каждом посте отдельно" },
    { key: "cards", label: "Карточек после склейки", value: stats.events.cards, tip: `Дубли склеены: ${formatNumber(stats.events.announcements - stats.events.cards)}` },
    { key: "marked", label: "Отмечено вами", value: stats.marked, tip: "С интересом или статусом" },
    { key: "going", label: "Собирались пойти", value: going, tip: "Возможно пойду, точно пойду и сходил" },
  ];
}

function planParts(stats: CityStats): Part[] {
  const count = (plan: Plan | null) => stats.plans.find((p) => (p.plan ?? null) === plan)?.count ?? 0;
  return [
    ...PLAN_ORDER.map((plan) => ({ key: plan, label: PLANS[plan].label, value: count(plan), color: PLAN_COLORS[plan], icon: PLANS[plan].icon })),
    { key: "none", label: "Без статуса", value: count(null), color: UNMARKED_COLOR },
  ];
}

function InterestChart({ stats }: { stats: CityStats }) {
  const rated = stats.interests.filter((i) => i.interest !== null).reverse();
  const unrated = stats.interests.find((i) => i.interest === null)?.count ?? 0;
  return (
    <div className="interest">
      <ColumnChart
        label="Карточки по интересу"
        height={150}
        series={[{ label: "Карточки", className: "series-accent" }]}
        columns={rated.map((i) => ({
          key: String(i.interest),
          label: (
            <span className="interest__tick">
              <Icon name="star" size={12} />
              {i.interest}
            </span>
          ),
          values: [i.count],
          tip: `${i.interest} из 5: ${cards(i.count)}`,
        }))}
      />
      <p className="interest__note">Без оценки — {cards(unrated)}</p>
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
          <th>Канал</th>
          <th>Постов</th>
          <th>Событий</th>
        </tr>
      </thead>
      <tbody>
        {stats.sources.map((source) => (
          <tr key={source.id}>
            <td className="source-stats__name">{source.title}</td>
            <td>
              <MiniBar value={source.posts} max={maxPosts} tip={`${source.title}: ${posts(source.posts)}`} quiet />
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
