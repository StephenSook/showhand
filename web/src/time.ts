// Pure timing helpers. The phone video is the master clock and the replay frames line up with
// its frames one to one, so frame index = time * fps.

export interface FramePick {
  i0: number;
  i1: number;
  alpha: number;
}

export function clamp(value: number, low: number, high: number): number {
  return Math.min(high, Math.max(low, value));
}

export function frameAt(timeS: number, fps: number, frames: number): FramePick {
  const position = clamp(timeS * fps, 0, frames - 1);
  const i0 = Math.floor(position);
  const i1 = Math.min(i0 + 1, frames - 1);
  return { i0, i1, alpha: position - i0 };
}

export function replayDuration(fps: number, frames: number): number {
  return (frames - 1) / fps;
}

export function secondAt(timeS: number, seconds: { start_s: number; end_s: number }[]): number {
  for (let i = 0; i < seconds.length; i++) {
    const row = seconds[i]!;
    if (timeS >= row.start_s && timeS < row.end_s) return i;
  }
  return timeS < 0 ? 0 : seconds.length - 1;
}

export function formatClock(timeS: number): string {
  const safe = Math.max(0, timeS);
  const minutes = Math.floor(safe / 60);
  const rest = safe - minutes * 60;
  return `${minutes}:${rest.toFixed(1).padStart(4, "0")}`;
}

// 2 -> "2", 6.1 -> "6.1", 0.25 -> "0.25"
export function seconds(value: number): string {
  return String(Number(value.toFixed(2)));
}

// A no-break space keeps the unit on the same line as its number, so "s." never wraps alone.
export const UNIT_SPACE = " ";

export function span(start: number, end: number): string {
  return `${seconds(start)} to ${seconds(end)}${UNIT_SPACE}s`;
}

export function spans(windows: { start_s: number; end_s: number }[]): string {
  const parts = windows.map((w) => span(w.start_s, w.end_s));
  if (parts.length === 0) return "nothing";
  if (parts.length === 1) return parts[0]!;
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}

export function sameWindows(
  a: { start_s: number; end_s: number }[],
  b: { start_s: number; end_s: number }[],
): boolean {
  return (
    a.length === b.length &&
    a.every((w, i) => Math.abs(w.start_s - b[i]!.start_s) < 1e-6 && Math.abs(w.end_s - b[i]!.end_s) < 1e-6)
  );
}
