import { describe, expect, it } from "vitest";
import { formatClock, frameAt, replayDuration, sameWindows, secondAt, seconds, span, spans } from "../src/time";
import { TimerClock } from "../src/clock";

describe("frameAt", () => {
  it("maps time to the matching frame pair", () => {
    expect(frameAt(0, 30, 184)).toEqual({ i0: 0, i1: 1, alpha: 0 });
    const mid = frameAt(1 / 30 + 0.5 / 30, 30, 184);
    expect(mid.i0).toBe(1);
    expect(mid.i1).toBe(2);
    expect(mid.alpha).toBeCloseTo(0.5, 6);
  });

  it("holds the last frame at and past the end", () => {
    expect(frameAt(99, 30, 184)).toEqual({ i0: 183, i1: 183, alpha: 0 });
    expect(frameAt(-1, 30, 184)).toEqual({ i0: 0, i1: 1, alpha: 0 });
  });

  it("gives the replay length from the last frame time", () => {
    expect(replayDuration(30, 184)).toBeCloseTo(6.1, 6);
  });
});

describe("secondAt", () => {
  const rows = [
    { start_s: 0, end_s: 1 },
    { start_s: 1, end_s: 2 },
    { start_s: 2, end_s: 2.1 },
  ];
  it("finds the window that holds the time", () => {
    expect(secondAt(0, rows)).toBe(0);
    expect(secondAt(1, rows)).toBe(1);
    expect(secondAt(2.05, rows)).toBe(2);
  });
  it("clamps outside the take", () => {
    expect(secondAt(-0.5, rows)).toBe(0);
    expect(secondAt(5, rows)).toBe(2);
  });
});

describe("text", () => {
  it("prints times without trailing zeros", () => {
    expect(seconds(2)).toBe("2");
    expect(seconds(6.1)).toBe("6.1");
    expect(span(1, 2)).toBe("1 to 2 s");
  });
  it("joins windows in reading order", () => {
    expect(spans([])).toBe("nothing");
    expect(spans([{ start_s: 0, end_s: 1 }])).toBe("0 to 1 s");
    expect(
      spans([
        { start_s: 1, end_s: 2 },
        { start_s: 4, end_s: 5 },
        { start_s: 5, end_s: 6 },
      ]),
    ).toBe("1 to 2 s, 4 to 5 s and 5 to 6 s");
  });
  it("formats the clock", () => {
    expect(formatClock(0)).toBe("0:00.0");
    expect(formatClock(6.13)).toBe("0:06.1");
    expect(formatClock(65.25)).toBe("1:05.3");
  });
  it("compares window lists by bounds", () => {
    expect(sameWindows([{ start_s: 1, end_s: 2 }], [{ start_s: 1, end_s: 2 }])).toBe(true);
    expect(sameWindows([{ start_s: 1, end_s: 2 }], [{ start_s: 2, end_s: 3 }])).toBe(false);
    expect(sameWindows([], [{ start_s: 2, end_s: 3 }])).toBe(false);
  });
});

describe("TimerClock", () => {
  it("advances only while playing, scaled by rate, and wraps at the end", () => {
    let now = 0;
    const clock = new TimerClock(6, () => now);
    now = 1000;
    expect(clock.time()).toBe(0);
    clock.play();
    now = 3000;
    expect(clock.time()).toBeCloseTo(2, 6);
    clock.setRate(0.5);
    now = 5000;
    expect(clock.time()).toBeCloseTo(3, 6);
    clock.pause();
    now = 9000;
    expect(clock.time()).toBeCloseTo(3, 6);
    clock.seek(5.5);
    clock.setRate(1);
    clock.play();
    now = 10000;
    expect(clock.time()).toBeCloseTo(0.5, 6);
  });
});
