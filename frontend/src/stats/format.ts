const NUMBER = new Intl.NumberFormat("ru-RU");
const PERCENT = new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 0 });

export const formatNumber = (value: number) => NUMBER.format(value);
export const formatShare = (part: number, whole: number) => PERCENT.format(whole ? part / whole : 0);
