import { useCollections, useSettings } from "../api/queries";

/** The collections the user switched on in settings and set up there: true once at least one exists. */
export function useCollectionsOn(): boolean {
  const enabled = useSettings().data?.collections_enabled ?? false;
  const collections = useCollections(enabled);
  return enabled && (collections.data?.length ?? 0) > 0;
}
