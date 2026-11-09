import type { ButtonHTMLAttributes } from "react";

import { Icon, type IconName } from "./Icon";

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  icon: IconName;
  /** What the button does: read by screen readers and shown on hover. */
  label: string;
  size?: number;
}

export function IconButton({ icon, label, size = 18, className = "", ...rest }: Props) {
  return (
    <button type="button" className={`icon-button ${className}`} aria-label={label} data-tip={label} {...rest}>
      <Icon name={icon} size={size} />
    </button>
  );
}
