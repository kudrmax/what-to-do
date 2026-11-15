import { ApiError } from "../api/client";

/** The backend's message when it answered; a lost connection means the app itself is not running. */
export function errorText(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "Can’t reach the app. It seems to have stopped. Start it again and reload the page.";
  return "Something went wrong. Try again.";
}
