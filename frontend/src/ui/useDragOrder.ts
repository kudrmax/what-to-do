import { useState, type DragEvent } from "react";

interface DragOrder {
  onMove: (from: number, to: number) => void;
  onEnd?: () => void;
}

export type DragRowProps = ReturnType<ReturnType<typeof useDragOrder>["rowProps"]>;

/** Rows of a list that change places while one of them is dragged over the others. */
export function useDragOrder({ onMove, onEnd }: DragOrder) {
  const [dragged, setDragged] = useState<number | null>(null);
  const rowProps = (index: number, name: string, fixed = false) => ({
    draggable: !fixed,
    onDragStart: (e: DragEvent) => {
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", name);
      setDragged(index);
    },
    onDragEnter: () => {
      if (dragged === null || fixed || dragged === index) return;
      onMove(dragged, index);
      setDragged(index);
    },
    onDragOver: (e: DragEvent) => e.preventDefault(),
    onDragEnd: () => {
      setDragged(null);
      onEnd?.();
    },
    onDrop: (e: DragEvent) => e.preventDefault(),
  });
  return { dragged, rowProps };
}
