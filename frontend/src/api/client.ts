import createClient from "openapi-fetch";

import type { components, paths } from "./schema";

type Schemas = components["schemas"];

export type City = Schemas["CityPublic"];
export type NewCity = Schemas["CityBase"];
export type Settings = Schemas["AppSettings"];
export type SettingsChange = Schemas["SettingsChange"];
export type Source = Schemas["SourcePublic"];
export type NewSource = Schemas["SourceRequest"];
export type SourceStatus = Schemas["SourceStatus"];
export type PotentialSource = Schemas["PotentialSourcePublic"];
export type PotentialSourceOrigin = Schemas["PotentialSourceOrigin"];
export type Tag = Schemas["TagPublic"];
export type EventCard = Schemas["EventPublic"];
export type Mention = Schemas["MentionPublic"];
export type Occurrence = Schemas["Occurrence"];
export type RefreshStatus = Schemas["RefreshProgress"];
export type Plan = Schemas["Plan"];
export type PlanFilter = Schemas["PlanFilter"];
export type Mark = Schemas["Mark"];
export type Conflict = Schemas["Conflict"];
export type UpdateStatus = Schemas["UpdateStatusView"];
export type UpdateProgress = Schemas["UpdateProgress"];
export type UpdateStep = Schemas["UpdateStep"];
export type ChangelogEntry = Schemas["ChangelogEntryView"];
export type FeedQuery = NonNullable<paths["/events"]["get"]["parameters"]["query"]>;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

interface Answer<T> {
  data?: T;
  error?: unknown;
  response: Response;
}

async function answer<T>(request: Promise<Answer<T>>): Promise<T> {
  const { data, error, response } = await request;
  if (!response.ok) {
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    throw new ApiError(response.status, typeof detail === "string" ? detail : `Ошибка ${response.status}`);
  }
  return data as T;
}

/** The local backend. Paths, parameters and bodies are checked against its schema at build time. */
export function createApi(baseUrl: string) {
  const client = createClient<paths>({ baseUrl, querySerializer: { array: { style: "form", explode: true } } });
  const event = (id: number) => ({ params: { path: { event_id: id } } });
  const source = (id: number) => ({ params: { path: { source_id: id } } });

  return {
    imageUrl: (path: string | null | undefined) => (path ? baseUrl + path : null),
    calendarFileUrl: (id: number) => `${baseUrl}/events/${id}/calendar.ics`,

    settings: () => answer(client.GET("/settings")),
    defaultSettings: () => answer(client.GET("/settings/defaults")),
    changeSettings: (body: SettingsChange) => answer(client.PATCH("/settings", { body })),

    cities: () => answer(client.GET("/cities")),
    addCity: (body: NewCity) => answer(client.POST("/cities", { body })),

    sources: () => answer(client.GET("/sources")),
    addSource: (body: NewSource) => answer(client.POST("/sources", { body })),
    renameSource: (id: number, title: string) => answer(client.PATCH("/sources/{source_id}", { ...source(id), body: { title } })),
    markSource: (id: number, status: SourceStatus) => answer(client.PUT("/sources/{source_id}/status", { ...source(id), body: { status } })),
    deleteSource: (id: number) => answer(client.DELETE("/sources/{source_id}", source(id))),
    potentialSources: () => answer(client.GET("/potential-sources")),
    adoptPotentialSource: (id: number) => answer(client.POST("/potential-sources/{potential_id}/source", { params: { path: { potential_id: id } } })),
    markPotentialSource: (id: number, processed: boolean) =>
      answer(client.PUT("/potential-sources/{potential_id}/processed", { params: { path: { potential_id: id } }, body: { processed } })),

    tags: () => answer(client.GET("/tags")),
    addTag: (name: string) => answer(client.POST("/tags", { body: { name } })),
    renameTag: (id: number, name: string) => answer(client.PATCH("/tags/{tag_id}", { params: { path: { tag_id: id } }, body: { name } })),

    feed: (query: FeedQuery) => answer(client.GET("/events", { params: { query } })),
    event: (id: number) => answer(client.GET("/events/{event_id}", event(id))),
    mentions: (id: number) => answer(client.GET("/events/{event_id}/mentions", event(id))),
    mark: (id: number, body: Mark) => answer(client.PUT("/events/{event_id}/mark", { ...event(id), body })),
    addDevNote: (id: number, text: string) => answer(client.POST("/events/{event_id}/dev-notes", { ...event(id), body: { text } })),
    merge: (id: number, otherId: number) => answer(client.POST("/events/{event_id}/merge", { ...event(id), body: { other_event_id: otherId } })),
    split: (id: number, mentionId: number) => answer(client.POST("/events/{event_id}/split", { ...event(id), body: { mention_id: mentionId } })),

    refresh: () => answer(client.POST("/refresh")),
    refreshStatus: () => answer(client.GET("/refresh")),

    version: () => answer(client.GET("/version")),
    updates: (force: boolean) => answer(client.GET("/updates", { params: { query: { force } } })),
    startUpdate: () => answer(client.POST("/update")),
    updateState: () => answer(client.GET("/update/state")),
    changelog: () => answer(client.GET("/changelog")),
    unseenChangelog: () => answer(client.GET("/changelog/unseen")),
    markChangelogSeen: () => answer(client.POST("/changelog/seen")),
  };
}

export type Api = ReturnType<typeof createApi>;
