import { Icon } from "./Icon";
import "./DragHandle.css";

export function DragHandle({ name, onMove }: { name: string; onMove: (step: -1 | 1) => void }) {
  return (
    <button
      type="button"
      className="drag-handle"
      aria-label={`Move “${name}” with the up and down arrows`}
      data-tip="Drag to reorder"
      onKeyDown={(e) => {
        if (e.key === "ArrowUp" || e.key === "ArrowDown") {
          e.preventDefault();
          onMove(e.key === "ArrowUp" ? -1 : 1);
        }
      }}
    >
      <Icon name="grip" size={16} />
    </button>
  );
}
