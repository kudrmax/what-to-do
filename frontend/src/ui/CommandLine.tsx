import { Icon } from "./Icon";
import { useCopy } from "./useCopy";
import "./CommandLine.css";

/** A command to paste into a terminal, with its own Copy button. */
export function CommandLine({ command }: { command: string }) {
  const { copy, copied, label } = useCopy(command);
  return (
    <div className="command-line">
      <code>{command}</code>
      <button type="button" className="button button--small command-line__copy" onClick={copy}>
        {copied && <Icon name="check" size={14} strokeWidth={2.4} />}
        {label}
      </button>
    </div>
  );
}
