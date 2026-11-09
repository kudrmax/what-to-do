import { useState } from "react";

import type { Plan } from "../api/client";
import { useFeed } from "../api/hooks";
import { DayFeed } from "../components/DayFeed";
import { ToggleChip } from "../components/Filters";
import { EmptyState, Screen } from "../components/Screen";
import { useActiveCity } from "../api/useActiveCity";
import { addDays } from "../domain/dates";

const RANGE_DAYS = 180;

/** Cards the user plans to visit, the same cards as in the feed. */
export function PlansScreen() {
  const { city, today } = useActiveCity();
  const [past, setPast] = useState(false);
  const [onlySure, setOnlySure] = useState(false);
  const plans: Plan[] = onlySure ? ["sure"] : past ? ["maybe", "sure", "went"] : ["maybe", "sure"];
  const range = today ? (past ? { start: addDays(today, -RANGE_DAYS), end: addDays(today, -1) } : { start: today, end: addDays(today, RANGE_DAYS) }) : {};
  const feed = useFeed({ ...range, plans, hideMarked: false }, today !== null);
  const occurrences = past ? [...(feed.data ?? [])].reverse() : (feed.data ?? []);

  return (
    <Screen
      title="Собираюсь пойти"
      filters={
        <div className="filters">
          <ToggleChip label="Предстоящие" on={!past} onChange={() => setPast(false)} />
          <ToggleChip label="Прошедшие" on={past} onChange={() => setPast(true)} />
          <ToggleChip label="Только «точно пойду»" on={onlySure} onChange={setOnlySure} />
        </div>
      }
    >
      {!city ? (
        <EmptyState title="Здесь пока пусто" link={{ to: "/sources", label: "Добавить город и источники" }} />
      ) : occurrences.length === 0 && feed.isSuccess ? (
        <EmptyState
          title={past ? "Прошедших планов нет" : "Планов пока нет"}
          text="Отметьте событие кнопкой «возможно пойду» или «точно пойду» — оно появится здесь."
        />
      ) : (
        today && <DayFeed occurrences={occurrences} today={today} />
      )}
    </Screen>
  );
}
