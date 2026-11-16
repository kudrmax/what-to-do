import { conventions } from "../domain/locale";

export const formatNumber = (value: number) => new Intl.NumberFormat(conventions().locale).format(value);
export const formatShare = (part: number, whole: number) => new Intl.NumberFormat(conventions().locale, { style: "percent", maximumFractionDigits: 0 }).format(whole ? part / whole : 0);
