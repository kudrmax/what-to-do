import { ApiError } from "../api/client";

/** The backend's message when it sent one, a generic one otherwise. */
export function errorText(error: unknown): string | null {
  if (!error) return null;
  return error instanceof ApiError ? error.message : "Не получилось, попробуйте ещё раз";
}
