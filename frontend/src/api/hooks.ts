import { createContext, useContext, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { ApiClient, FeedQuery, Mark, SettingsChange } from "./client";

export const ApiContext = createContext<ApiClient | null>(null);

export function useApi(): ApiClient {
  const api = useContext(ApiContext);
  if (!api) throw new Error("ApiContext is not provided");
  return api;
}

const keys = {
  settings: ["settings"] as const,
  cities: ["cities"] as const,
  sources: ["sources"] as const,
  tags: ["tags"] as const,
  feed: (query: FeedQuery) => ["feed", query] as const,
  feedAll: ["feed"] as const,
  event: (id: number) => ["event", id] as const,
  eventAll: ["event"] as const,
  refresh: ["refresh"] as const,
};

export const useSettings = () => {
  const api = useApi();
  return useQuery({ queryKey: keys.settings, queryFn: api.settings });
};

export const useCities = () => {
  const api = useApi();
  return useQuery({ queryKey: keys.cities, queryFn: api.cities });
};

export const useSources = (enabled = true) => {
  const api = useApi();
  return useQuery({ queryKey: keys.sources, queryFn: api.sources, enabled });
};

export const useTags = () => {
  const api = useApi();
  return useQuery({ queryKey: keys.tags, queryFn: api.tags });
};

export const useFeed = (query: FeedQuery, enabled = true) => {
  const api = useApi();
  return useQuery({ queryKey: keys.feed(query), queryFn: () => api.feed(query), enabled, placeholderData: (previous) => previous });
};

export const useEvent = (id: number) => {
  const api = useApi();
  return useQuery({ queryKey: keys.event(id), queryFn: () => api.event(id) });
};

/** Everything that shows cards is stale after a card changes. */
function useInvalidateCards() {
  const client = useQueryClient();
  return () => Promise.all([client.invalidateQueries({ queryKey: keys.feedAll }), client.invalidateQueries({ queryKey: keys.eventAll })]);
}

function useInvalidateCity() {
  const client = useQueryClient();
  return () => client.invalidateQueries();
}

export const useSetMark = () => {
  const api = useApi();
  const invalidate = useInvalidateCards();
  return useMutation({ mutationFn: ({ id, mark }: { id: number; mark: Mark }) => api.mark(id, mark), onSuccess: invalidate });
};

export const useSplit = () => {
  const api = useApi();
  const invalidate = useInvalidateCards();
  return useMutation({ mutationFn: ({ id, mentionId }: { id: number; mentionId: number }) => api.split(id, mentionId), onSuccess: invalidate });
};

export const useMerge = () => {
  const api = useApi();
  const invalidate = useInvalidateCards();
  return useMutation({ mutationFn: ({ id, otherId }: { id: number; otherId: number }) => api.merge(id, otherId), onSuccess: invalidate });
};

export const useChangeSettings = () => {
  const api = useApi();
  const invalidate = useInvalidateCity();
  return useMutation({ mutationFn: (change: SettingsChange) => api.changeSettings(change), onSuccess: invalidate });
};

export const useAddCity = () => {
  const api = useApi();
  const invalidate = useInvalidateCity();
  return useMutation({ mutationFn: ({ name, timezone }: { name: string; timezone: string }) => api.addCity(name, timezone), onSuccess: invalidate });
};

export const useAddSource = () => {
  const api = useApi();
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ link, title }: { link: string; title: string }) => api.addSource(link, title),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.sources }),
  });
};

export const useDeleteSource = () => {
  const api = useApi();
  const invalidate = useInvalidateCity();
  return useMutation({ mutationFn: (id: number) => api.deleteSource(id), onSuccess: invalidate });
};

export const useRenameSource = () => {
  const api = useApi();
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => api.renameSource(id, title),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.sources }),
  });
};

/** Refresh status; polls while a refresh runs and reloads the cards once it ends. */
export const useRefresh = () => {
  const api = useApi();
  const client = useQueryClient();
  const status = useQuery({
    queryKey: keys.refresh,
    queryFn: api.refreshStatus,
    refetchInterval: (query) => (query.state.data?.running ? 1500 : false),
  });
  const start = useMutation({ mutationFn: api.refresh, onSuccess: (data) => client.setQueryData(keys.refresh, data) });
  const running = status.data?.running ?? false;
  useEffect(() => {
    if (status.data && !status.data.running && status.data.finished_at) {
      client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== "refresh" });
    }
  }, [client, status.data?.running, status.data?.finished_at]); // eslint-disable-line react-hooks/exhaustive-deps
  return { status: status.data, running: running || start.isPending, start: () => start.mutate() };
};

export const useAddTag = () => {
  const api = useApi();
  const client = useQueryClient();
  return useMutation({ mutationFn: (name: string) => api.addTag(name), onSuccess: () => client.invalidateQueries({ queryKey: keys.tags }) });
};

export const useRenameTag = () => {
  const api = useApi();
  const invalidate = useInvalidateCity();
  return useMutation({ mutationFn: ({ id, name }: { id: number; name: string }) => api.renameTag(id, name), onSuccess: invalidate });
};
