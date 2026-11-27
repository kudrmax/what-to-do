import { READERS, type Reader } from "../domain/readers";
import { useSettings } from "./queries";

/** The reader chosen in settings; Claude until the settings load. */
export function useReader(): Reader {
  const settings = useSettings();
  return READERS[settings.data?.llm_provider ?? "claude"];
}
