import { SECTIONS } from "../app/routes";
import { EmptyState } from "../ui/Screen";

export function NoCity() {
  return <EmptyState title="Nothing here yet" text="Add a city, then Telegram channels that post events. Events will appear after a refresh." link={{ to: SECTIONS.settings.path, label: "Add city" }} />;
}
