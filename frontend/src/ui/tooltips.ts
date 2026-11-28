const EDGE_GAP = 8;
const OFFSET = 6;

export type TipAlign = "start" | "center" | "end";

interface Span {
  left: number;
  right: number;
}

/** A tooltip sits centred on its element; when that would cross an edge of the window it lines up with the element's edge on that side instead. */
export function tipAlign(element: Span, tipWidth: number, windowWidth: number): TipAlign {
  const centre = (element.left + element.right) / 2;
  if (centre + tipWidth / 2 > windowWidth - EDGE_GAP) return "end";
  if (centre - tipWidth / 2 < EDGE_GAP) return "start";
  return "center";
}

/** Every data-tip tooltip sits centred above its element; near an edge of the window it lines up with the element's edge, near the top it goes below. */
export function keepTooltipsInView(doc: Document = document): void {
  const probe = doc.createElement("span");
  probe.className = "tip-probe";
  probe.setAttribute("aria-hidden", "true");
  doc.body.append(probe);

  const place = (event: Event) => {
    const element = (event.target as Element | null)?.closest?.<HTMLElement>("[data-tip]");
    if (!element) return;
    probe.textContent = element.dataset.tip ?? "";
    const box = element.getBoundingClientRect();
    element.dataset.tipAlign = tipAlign(box, probe.offsetWidth, doc.documentElement.clientWidth);
    element.toggleAttribute("data-tip-below", box.top - OFFSET - probe.offsetHeight < EDGE_GAP);
  };
  doc.addEventListener("pointerover", place);
  doc.addEventListener("focusin", place);
}
