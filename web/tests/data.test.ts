import { describe, expect, it } from "vitest";
import { checkFrames, checkGrades, checkIndex, checkReplay, type ReplayManifest } from "../src/data";
import { limitText, METRICS, reasonLabel, reasonList, valueText, decidedByText } from "../src/copy";

function replay(frames = 3, geoms = 2): ReplayManifest {
  return {
    schema_version: 1,
    take: "take_0001",
    fps: 30,
    frames,
    geoms: Array.from({ length: geoms }, (_, i) => ({ node: `g${i}`, body: i === 0 ? "pelvis" : "link" })),
    frame_layout: "float32 [frame][geom][x, y, z, qw, qx, qy, qz]",
    frame_times: Array.from({ length: frames }, (_, i) => ({
      frame: i,
      sim_time_s: i / 30,
      out_of_balance: "0",
      fall_event: "0",
    })),
    frames_sha256: "0".repeat(64),
  };
}

function grades() {
  const rules = {
    pass: true,
    reason_codes: [],
    tracking_mean_abs_error_rad: 0.1,
    tracking_p95_abs_error_rad: 0.2,
    root_tilt_max_deg: 3,
    root_height_min_m: 0.7,
    foot_slip_max_m_s: 0,
    foot_slip_seconds: 0,
    out_of_balance_seconds: 0,
    falls: 0,
  };
  return {
    schema_version: 1,
    take: "take_0001",
    duration_s: 1.5,
    overall: { pass: true, reason_codes: [] },
    cutoffs: { tracking_p95_abs_error_rad: 1 },
    models: { cosmos: "c", supervl: "s", fusion: "f" },
    seconds: [
      { start_s: 0, end_s: 1, rules, cosmos: null, supervl: null },
      { start_s: 1, end_s: 1.5, rules, cosmos: null, supervl: null },
    ],
    fusion: {
      decided_by: "nemotron",
      status: "passed_first",
      request_id: "r",
      cost_usd: 0.0001,
      attempts: [],
      final: { decision: "reshow", evidence_refs: [], reshow_windows: [{ start_s: 0, end_s: 1, reason: "x" }] },
    },
  };
}

describe("checkIndex", () => {
  it("accepts a take list and refuses an empty or malformed one", () => {
    expect(checkIndex({ schema_version: 1, takes: [{ take: "take_0525", label: "L", decision: "reshow" }] })).toEqual([
      { take: "take_0525", label: "L", decision: "reshow" },
    ]);
    expect(() => checkIndex({ schema_version: 1, takes: [] })).toThrow(/lists no takes/);
    expect(() => checkIndex({ schema_version: 1, takes: [{ take: "../etc" }] })).toThrow(/no take id/);
    expect(() => checkIndex({ schema_version: 2, takes: [] })).toThrow(/schema_version/);
  });
});

describe("checkReplay", () => {
  it("accepts a well-formed manifest", () => {
    expect(checkReplay(replay(), "take_0001").frames).toBe(3);
  });
  it("refuses a manifest for another take or with missing frame rows", () => {
    expect(() => checkReplay(replay(), "take_0002")).toThrow(/names take take_0001/);
    const short = { ...replay(), frame_times: replay().frame_times.slice(1) };
    expect(() => checkReplay(short, "take_0001")).toThrow(/2 rows for 3 frames/);
  });
});

describe("checkFrames", () => {
  it("accepts exactly frames x geoms x 7 floats", () => {
    const r = replay(3, 2);
    expect(checkFrames(new Float32Array(3 * 2 * 7).buffer, r).length).toBe(42);
  });
  it("refuses a file of the wrong size", () => {
    expect(() => checkFrames(new Float32Array(41).buffer, replay(3, 2))).toThrow(/164 bytes, expected 168/);
  });
  it("refuses a value that is not finite", () => {
    const values = new Float32Array(42);
    values[10] = Number.NaN;
    expect(() => checkFrames(values.buffer, replay(3, 2))).toThrow(/value 10/);
  });
});

describe("checkGrades", () => {
  it("accepts contiguous seconds and an in-range re-show list", () => {
    expect(checkGrades(grades(), "take_0001").seconds).toHaveLength(2);
  });
  it("refuses a gap between seconds", () => {
    const g = grades();
    g.seconds[1]!.start_s = 1.2;
    expect(() => checkGrades(g, "take_0001")).toThrow(/does not continue/);
  });
  it("refuses a re-show window outside the take", () => {
    const g = grades();
    g.fusion.final.reshow_windows = [{ start_s: 1, end_s: 3, reason: "x" }];
    expect(() => checkGrades(g, "take_0001")).toThrow(/outside the take/);
  });
});

describe("copy", () => {
  it("names known codes and keeps unknown ones readable", () => {
    expect(reasonLabel("foot_slip")).toBe("foot slip");
    expect(reasonLabel("brand_new_code")).toBe("brand new code");
    expect(reasonList(["foot_slip", "out_of_balance"])).toBe("foot slip and out of balance");
  });
  it("prints limits from the cutoffs it is given, never its own copy", () => {
    const p95 = METRICS.find((m) => m.field === "tracking_p95_abs_error_rad")!;
    expect(limitText(p95, { tracking_p95_abs_error_rad: 1 })).toBe("at most 1 rad");
    expect(limitText(p95, {})).toBe("no limit recorded");
    const height = METRICS.find((m) => m.field === "root_height_min_m")!;
    expect(limitText(height, { root_height_min_m: 0.2 })).toBe("at least 0.2 m");
    expect(valueText(height, 0.785715)).toBe("0.79 m");
  });
  it("explains each fusion outcome the grader writes", () => {
    expect(decidedByText("deterministic_fallback", "fallback_after_guard_refusals")).toMatch(/fell back/);
    expect(decidedByText("nemotron", "passed_after_retry")).toMatch(/retry/);
    expect(decidedByText("nemotron", "passed_first")).toMatch(/first answer/);
  });
});
