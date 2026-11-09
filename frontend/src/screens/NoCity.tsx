import { SECTIONS } from "../app/routes";
import { EmptyState } from "../ui/Screen";

export function NoCity() {
  return <EmptyState title="Здесь пока пусто" text="Добавьте город, потом Telegram-каналы с афишами — события появятся после обновления." link={{ to: SECTIONS.settings.path, label: "Добавить город" }} />;
}
