// The page's one clock. With the phone video loaded, the video element is the clock, so the
// robot can never drift from the person. Without it (a checkout that has no clips), a timer
// stands in and the page says so.

export interface Clock {
  readonly kind: "video" | "timer";
  readonly duration: number;
  time(): number;
  playing(): boolean;
  play(): void;
  pause(): void;
  seek(timeS: number): void;
  setRate(rate: number): void;
}

export class VideoClock implements Clock {
  readonly kind = "video";
  constructor(
    private readonly video: HTMLVideoElement,
    readonly duration: number,
  ) {}
  time(): number {
    return this.video.currentTime;
  }
  playing(): boolean {
    return !this.video.paused && !this.video.ended;
  }
  play(): void {
    // A blocked autoplay rejects; the play button stays in its paused state and the user can retry.
    this.video.play().catch(() => undefined);
  }
  pause(): void {
    this.video.pause();
  }
  seek(timeS: number): void {
    this.video.currentTime = Math.min(Math.max(0, timeS), this.duration);
  }
  setRate(rate: number): void {
    this.video.playbackRate = rate;
  }
}

export class TimerClock implements Clock {
  readonly kind = "timer";
  private startedAt: number | null = null;
  private offset = 0;
  private rate = 1;
  constructor(
    readonly duration: number,
    private readonly now: () => number = () => performance.now(),
  ) {}
  time(): number {
    if (this.startedAt === null) return this.offset;
    const elapsed = ((this.now() - this.startedAt) / 1000) * this.rate;
    return (this.offset + elapsed) % this.duration;
  }
  playing(): boolean {
    return this.startedAt !== null;
  }
  play(): void {
    if (this.startedAt === null) this.startedAt = this.now();
  }
  pause(): void {
    this.offset = this.time();
    this.startedAt = null;
  }
  seek(timeS: number): void {
    this.offset = Math.min(Math.max(0, timeS), this.duration);
    if (this.startedAt !== null) this.startedAt = this.now();
  }
  setRate(rate: number): void {
    const current = this.time();
    this.rate = rate;
    this.offset = current;
    if (this.startedAt !== null) this.startedAt = this.now();
  }
}

export async function videoReady(video: HTMLVideoElement, src: string, timeoutMs = 8000): Promise<boolean> {
  return new Promise((resolve) => {
    const done = (ok: boolean) => {
      clearTimeout(timer);
      video.removeEventListener("loadedmetadata", onReady);
      video.removeEventListener("error", onError);
      resolve(ok);
    };
    const onReady = () => done(true);
    const onError = () => done(false);
    const timer = setTimeout(() => done(false), timeoutMs);
    video.addEventListener("loadedmetadata", onReady);
    video.addEventListener("error", onError);
    video.src = src;
    video.load();
  });
}
