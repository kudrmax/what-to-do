export interface InterfaceTiming {
  action: string;
  screen: string;
  phases: Record<string, number>;
  blocked: number;
}

type Send = (timing: InterfaceTiming) => void;

const FREEZE_MS = 150;
const BEAT_MS = 50;

const nextPaint = () => new Promise<void>((done) => requestAnimationFrame(() => requestAnimationFrame(() => done())));
const screen = () => window.location.pathname + window.location.search;

/** One user action followed through its phases until the page has drawn the result. */
export class Measurement {
  private readonly started = performance.now();
  private readonly phases: Record<string, number> = {};
  private blocked = 0;
  private lastBeat = this.started;
  private readonly beat: ReturnType<typeof setInterval>;

  private readonly action: string;
  private readonly send: Send;

  constructor(action: string, send: Send) {
    this.action = action;
    this.send = send;
    this.beat = setInterval(() => this.onBeat(), 0);
  }

  phase(name: string): void {
    this.phases[name] = performance.now() - this.started;
  }

  async finish(): Promise<void> {
    await nextPaint();
    this.onBeat();
    clearInterval(this.beat);
    this.phase("shown");
    this.send({ action: this.action, screen: screen(), phases: this.phases, blocked: this.blocked });
  }

  private onBeat(): void {
    const now = performance.now();
    this.blocked = Math.max(this.blocked, now - this.lastBeat);
    this.lastBeat = now;
  }
}

/** Measures how long the interface takes to answer and reports every freeze, so slowness shows up in the app log. */
export class InterfaceTimings {
  private send: Send = () => {};
  private watcher: ReturnType<typeof setInterval> | undefined;

  connect(send: Send): void {
    this.send = send;
    this.watchFreezes();
  }

  disconnect(): void {
    clearInterval(this.watcher);
    this.send = () => {};
  }

  start(action: string): Measurement {
    return new Measurement(action, (timing) => this.send(timing));
  }

  private watchFreezes(): void {
    let last = performance.now();
    clearInterval(this.watcher);
    this.watcher = setInterval(() => {
      const now = performance.now();
      const gap = now - last;
      last = now;
      if (!document.hidden && gap > FREEZE_MS + BEAT_MS) this.send({ action: "freeze", screen: screen(), phases: {}, blocked: gap - BEAT_MS });
    }, BEAT_MS);
  }
}

export const timings = new InterfaceTimings();

export function timingsSender(baseUrl: string): Send {
  return (timing) => {
    void fetch(`${baseUrl}/timings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(timing), keepalive: true }).catch(() => {});
  };
}
