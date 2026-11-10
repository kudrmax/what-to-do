// Points at an element before a screenshot: the rest of the page is dimmed, the element keeps
// its light and gets a soft ring in the app's accent colour; an optional caption sits next to it
// in the app's own type. Inject with the page's evaluate, then call
// window.__annotate({selector, label}).
(() => {
  // How much the page around the element is dimmed.
  const DIM = 0.6
  // Room between the element and the ring.
  const PAD = 14
  const RADIUS = 14
  const RING = 2
  const GLOW = 12
  const CAPTION_SIZE = 14
  const CAPTION_PAD_X = 12
  const CAPTION_PAD_Y = 7
  const CAPTION_GAP = 12
  // Nothing is drawn closer than this to the viewport's edge.
  const MARGIN = 12
  const OVERLAY_ID = '__annotations'
  const SVG_NS = 'http://www.w3.org/2000/svg'

  const svg = (name, attrs) => {
    const node = document.createElementNS(SVG_NS, name)
    Object.entries(attrs).forEach(([key, value]) => node.setAttribute(key, String(value)))
    return node
  }

  const token = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()

  const clamp = (value, min, max) => Math.max(min, Math.min(value, max))

  const spotlight = (root, hole, accent) => {
    const mask = svg('mask', { id: `${OVERLAY_ID}-hole` })
    mask.appendChild(svg('rect', { x: 0, y: 0, width: '100%', height: '100%', fill: '#fff' }))
    mask.appendChild(svg('rect', { ...hole, rx: RADIUS, fill: '#000' }))
    const glow = svg('filter', { id: `${OVERLAY_ID}-glow`, x: '-50%', y: '-50%', width: '200%', height: '200%' })
    glow.appendChild(svg('feDropShadow', { dx: 0, dy: 0, stdDeviation: GLOW / 2, 'flood-color': accent, 'flood-opacity': 0.6 }))
    const defs = svg('defs', {})
    defs.append(mask, glow)
    root.appendChild(defs)
    root.appendChild(svg('rect', {
      x: 0, y: 0, width: '100%', height: '100%', fill: '#000', 'fill-opacity': DIM, mask: `url(#${OVERLAY_ID}-hole)`,
    }))
    root.appendChild(svg('rect', {
      ...hole, rx: RADIUS, fill: 'none', stroke: accent, 'stroke-width': RING, filter: `url(#${OVERLAY_ID}-glow)`,
    }))
  }

  // The caption sits below the element when there is room, otherwise above it.
  const caption = (root, text, hole) => {
    if (!text) return
    const group = svg('g', {})
    const pill = svg('rect', { rx: 8, fill: token('--bg'), stroke: token('--line'), 'stroke-width': 1 })
    const words = svg('text', {
      fill: token('--text'), 'font-size': CAPTION_SIZE, 'font-weight': 500,
      'font-family': getComputedStyle(document.body).fontFamily, 'dominant-baseline': 'middle',
    })
    words.textContent = text
    group.append(pill, words)
    root.appendChild(group)
    const width = words.getBBox().width + 2 * CAPTION_PAD_X
    const height = CAPTION_SIZE + 2 * CAPTION_PAD_Y
    const x = clamp(hole.x, MARGIN, window.innerWidth - MARGIN - width)
    const below = hole.y + hole.height + CAPTION_GAP
    const y = below + height <= window.innerHeight - MARGIN ? below : hole.y - CAPTION_GAP - height
    Object.entries({ x, y, width, height }).forEach(([key, value]) => pill.setAttribute(key, String(value)))
    words.setAttribute('x', String(x + CAPTION_PAD_X))
    words.setAttribute('y', String(y + height / 2))
  }

  window.__annotate = ({ selector, label: text }) => {
    const target = document.querySelector(selector)
    if (!target) throw new Error(`annotate: no element for ${selector}`)
    target.scrollIntoView({ block: 'center', inline: 'center' })
    const box = target.getBoundingClientRect()
    window.__clearAnnotations()
    const root = svg('svg', { id: OVERLAY_ID, width: '100%', height: '100%' })
    root.style.cssText = 'position:fixed;inset:0;pointer-events:none;z-index:2147483647'
    document.body.appendChild(root)
    const hole = { x: box.left - PAD, y: box.top - PAD, width: box.width + 2 * PAD, height: box.height + 2 * PAD }
    spotlight(root, hole, token('--accent'))
    caption(root, text, hole)
  }

  window.__clearAnnotations = () => document.getElementById(OVERLAY_ID)?.remove()
})()
