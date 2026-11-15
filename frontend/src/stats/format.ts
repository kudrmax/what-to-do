const NUMBER = new Intl.NumberFormat("en-GB");
const PERCENT = new Intl.NumberFormat("en-GB", { style: "percent", maximumFractionDigits: 0 });

export const formatNumber = (value: number) => NUMBER.format(value);
export const formatShare = (part: number, whole: number) => PERCENT.format(whole ? part / whole : 0);
