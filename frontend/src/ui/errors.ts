import { ApiError } from "../api/client";

/** The backend's message when it answered; a lost connection means the app itself is not running. */
export function errorText(error: unknown): string | null {
  if (!error) return null;
  if (error instanceof ApiError) return error.message;
  if (error instanceof TypeError) return "Нет связи с приложением: похоже, оно остановлено. Запустите его снова и обновите страницу.";
  return "Не получилось, попробуйте ещё раз";
}
