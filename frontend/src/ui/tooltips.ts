const EDGE_GAP = 8;
const OFFSET = 6;

/** Every data-tip tooltip sits centred above its element; near an edge of the window it moves inwards or below. */
export function keepTooltipsInView(doc: Document = document): void {
  const probe = doc.createElement("span");
  probe.className = "tip-probe";
  probe.setAttribute("aria-hidden", "true");
  doc.body.append(probe);

  const place = (event: Event) => {
    const element = (event.target as Element | null)?.closest?.<HTMLElement>("[data-tip]");
    if (!element) return;
    probe.textContent = element.dataset.tip ?? "";
    const width = probe.offsetWidth;
    const box = element.getBoundingClientRect();
    const centred = box.left + box.width / 2 - width / 2;
    const inside = Math.min(Math.max(centred, EDGE_GAP), doc.documentElement.clientWidth - EDGE_GAP - width);
    element.style.setProperty("--tip-shift", `${inside - centred}px`);
    element.toggleAttribute("data-tip-below", box.top - OFFSET - probe.offsetHeight < EDGE_GAP);
  };
  doc.addEventListener("pointerover", place);
  doc.addEventListener("focusin", place);
}
