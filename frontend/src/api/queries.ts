import { createContext, useContext, useEffect } from "react";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";

import type { Api, FeedQuery, Mark, NewCity, NewSource, SettingsChange } from "./client";

export const ApiContext = createContext<Api | null>(null);

export function useApi(): Api {
  const api = useContext(ApiContext);
  if (!api) throw new Error("ApiContext is not provided");
  return api;
}

const keys = {
  settings: ["settings"],
  defaults: ["settings", "defaults"],
  cities: ["cities"],
  sources: ["sources"],
  tags: ["tags"],
  feed: ["feed"],
  event: ["event"],
  refresh: ["refresh"],
} satisfies Record<string, QueryKey>;

/** What a change makes stale: the cards, or everything that depends on the active city. */
const STALE = {
  cards: [keys.feed, keys.event],
  sources: [keys.sources],
  tags: [keys.tags, keys.feed, keys.event],
  settings: [keys.settings],
  city: [[]] as QueryKey[],
};

function useApiQuery<T>(key: QueryKey, load: (api: Api) => Promise<T>, enabled = true) {
  const api = useApi();
  return useQuery({ queryKey: key, queryFn: () => load(api), enabled, placeholderData: (previous) => previous });
}

function useApiMutation<A, R>(run: (api: Api, args: A) => Promise<R>, stale: QueryKey[]) {
  const api = useApi();
  const client = useQueryClient();
  return useMutation({
    mutationFn: (args: A) => run(api, args),
    onSuccess: () => Promise.all(stale.map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
}

export const useSettings = () => useApiQuery(keys.settings, (api) => api.settings());
export const useDefaultSettings = () => useApiQuery(keys.defaults, (api) => api.defaultSettings());
export const useCities = () => useApiQuery(keys.cities, (api) => api.cities());
export const useSources = (enabled = true) => useApiQuery(keys.sources, (api) => api.sources(), enabled);
export const useTags = () => useApiQuery(keys.tags, (api) => api.tags());
export const useFeed = (query: FeedQuery, enabled = true) => useApiQuery([...keys.feed, query], (api) => api.feed(query), enabled);
export const useEvent = (id: number) => useApiQuery([...keys.event, id], (api) => api.event(id));
export const useMentions = (id: number) => useApiQuery([...keys.event, id, "mentions"], (api) => api.mentions(id));

export const useSetMark = () => useApiMutation((api, { id, mark }: { id: number; mark: Mark }) => api.mark(id, mark), STALE.cards);
export const useAddDevNote = () => useApiMutation((api, { id, text }: { id: number; text: string }) => api.addDevNote(id, text), []);
export const useMerge = () => useApiMutation((api, { id, otherId }: { id: number; otherId: number }) => api.merge(id, otherId), STALE.cards);
export const useSplit = () => useApiMutation((api, { id, mentionId }: { id: number; mentionId: number }) => api.split(id, mentionId), STALE.cards);
export const useChangeSettings = () => useApiMutation((api, change: SettingsChange) => api.changeSettings(change), STALE.city);
export const useAddCity = () => useApiMutation((api, city: NewCity) => api.addCity(city), STALE.city);
export const useAddSource = () => useApiMutation((api, source: NewSource) => api.addSource(source), STALE.sources);
export const useRenameSource = () => useApiMutation((api, { id, title }: { id: number; title: string }) => api.renameSource(id, title), STALE.sources);
export const useDeleteSource = () => useApiMutation((api, id: number) => api.deleteSource(id), STALE.city);
export const useAddTag = () => useApiMutation((api, name: string) => api.addTag(name), STALE.tags);
export const useRenameTag = () => useApiMutation((api, { id, name }: { id: number; name: string }) => api.renameTag(id, name), STALE.tags);

/** Refresh status; polls while a refresh runs and reloads everything else once it ends. */
export function useRefresh() {
  const api = useApi();
  const client = useQueryClient();
  const status = useQuery({
    queryKey: keys.refresh,
    queryFn: () => api.refreshStatus(),
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
  });
  const start = useMutation({ mutationFn: () => api.refresh(), onSuccess: (data) => client.setQueryData(keys.refresh, data) });
  const finishedAt = status.data?.running ? null : status.data?.finished_at;
  useEffect(() => {
    if (finishedAt) client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== keys.refresh[0] });
  }, [client, finishedAt]);
  return { status: status.data, running: (status.data?.running ?? false) || start.isPending, start: () => start.mutate() };
}
