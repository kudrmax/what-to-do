import type { components } from "./schema";

type Schemas = components["schemas"];

export type City = Schemas["CityOut"];
export type Settings = Schemas["SettingsOut"];
export type SettingsChange = Schemas["SettingsIn"];
export type Source = Schemas["SourceOut"];
export type Tag = Schemas["TagOut"];
export type EventCard = Schemas["EventOut"];
export type EventDetail = Schemas["EventDetailOut"];
export type Mention = Schemas["MentionOut"];
export type Occurrence = Schemas["OccurrenceOut"];
export type RefreshStatus = Schemas["RefreshOut"];
export type Plan = NonNullable<Schemas["MarkIn"]["plan"]>;
export type Mark = Schemas["MarkIn"];

export interface FeedQuery {
  start?: string;
  end?: string;
  tags?: string[];
  sources?: number[];
  plans?: Plan[];
  onlyTimed?: boolean;
  hideMultiday?: boolean;
  hideMarked?: boolean;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Talks to the local backend; the only place that knows its URLs. */
export class ApiClient {
  private readonly base: string;

  constructor(base: string) {
    this.base = base;
  }

  imageUrl(path: string | null): string | null {
    return path ? this.base + path : null;
  }

  settings = () => this.request<Settings>("GET", "/settings");
  changeSettings = (change: SettingsChange) => this.request<Settings>("PATCH", "/settings", change);
  cities = () => this.request<City[]>("GET", "/cities");
  addCity = (name: string, timezone: string) => this.request<City>("POST", "/cities", { name, timezone });

  sources = () => this.request<Source[]>("GET", "/sources");
  addSource = (link: string, title: string) => this.request<Source>("POST", "/sources", { link, title: title || null });
  renameSource = (id: number, title: string) => this.request<Source>("PATCH", `/sources/${id}`, { title });
  deleteSource = (id: number) => this.request<void>("DELETE", `/sources/${id}`);

  tags = () => this.request<Tag[]>("GET", "/tags");
  addTag = (name: string) => this.request<Tag>("POST", "/tags", { name });
  renameTag = (id: number, name: string) => this.request<Tag>("PATCH", `/tags/${id}`, { name });

  feed = (query: FeedQuery) => this.request<Occurrence[]>("GET", "/events?" + feedParams(query));
  event = (id: number) => this.request<EventDetail>("GET", `/events/${id}`);
  mark = (id: number, mark: Mark) => this.request<EventCard>("PUT", `/events/${id}/mark`, mark);
  merge = (id: number, otherId: number) =>
    this.request<EventDetail>("POST", `/events/${id}/merge`, { other_event_id: otherId });
  split = (id: number, mentionId: number) =>
    this.request<EventDetail>("POST", `/events/${id}/split`, { mention_id: mentionId });

  refresh = () => this.request<RefreshStatus>("POST", "/refresh");
  refreshStatus = () => this.request<RefreshStatus>("GET", "/refresh");

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const response = await fetch(this.base + path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) {
      throw new ApiError(response.status, await errorText(response));
    }
    return (response.status === 204 ? undefined : await response.json()) as T;
  }
}

export function feedParams(query: FeedQuery): string {
  const params = new URLSearchParams();
  if (query.start) params.set("start", query.start);
  if (query.end) params.set("end", query.end);
  query.tags?.forEach((tag) => params.append("tags", tag));
  query.sources?.forEach((id) => params.append("sources", String(id)));
  query.plans?.forEach((plan) => params.append("plans", plan));
  if (query.onlyTimed) params.set("only_timed", "true");
  if (query.hideMultiday) params.set("hide_multiday", "true");
  if (query.hideMarked !== undefined) params.set("hide_marked", String(query.hideMarked));
  return params.toString();
}

async function errorText(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // not JSON: fall through
  }
  return `Ошибка ${response.status}`;
}
