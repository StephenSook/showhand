import { describe, expect, it } from "vitest";
import {
  checkFrames,
  checkGrades,
  checkIndex,
  checkReplay,
  checkResidual,
  checkResidualAgainstTakes,
  type Grades,
  type ReplayManifest,
} from "../src/data";
import {
  callLine,
  callParts,
  catchLine,
  decidedByText,
  fusionCostLine,
  gradeWord,
  guardCaught,
  limitText,
  METRICS,
  outsideView,
  reasonLabel,
  reasonList,
  residualSentences,
  unsentFailingSeconds,
  unsentSentence,
  valueText,
  windowReason,
} from "../src/copy";

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
    runtime: {
      gem_x_offline_s: 1,
      replay_process_wall_s: 2,
      cosmos_model_load_s: 3,
      supervl_wall_s: 4,
      supervl_cost_usd: 0.001,
    } as Record<string, unknown>,
  };
}

// The shape tools/residual_report.py writes. These labels are test fixtures, never a result.
function residual() {
  return {
    schema_version: 1,
    label_source: "human",
    n: 2,
    fused_agreement: 0.5,
    tracking_agreement: 1.0,
    fused_kappa: 0.0,
    tracking_kappa: null as number | null,
    status: "evaluation_invalid",
    why: "the report's own reason",
    labels: [
      { take_id: "take_0001", human: "accept", fused_judge: "reshow", tracking_alone: "accept" },
      { take_id: "take_0002", human: "accept", fused_judge: "accept", tracking_alone: "accept" },
    ],
    inputs: { grades: "results/residual/human_grades.json" },
  };
}

function rerate(r: ReturnType<typeof residual>) {
  const match = (field: "fused_judge" | "tracking_alone") =>
    r.labels.filter((row) => row[field] === row.human).length / r.labels.length;
  return { ...r, n: r.labels.length, fused_agreement: match("fused_judge"), tracking_agreement: match("tracking_alone") };
}

describe("checkResidual", () => {
  it("accepts the report tools/residual_report.py writes", () => {
    expect(checkResidual(residual()).labels).toHaveLength(2);
  });
  it("refuses labels that did not come from a human", () => {
    expect(() => checkResidual({ ...residual(), label_source: "synthetic" })).toThrow(/label_source is synthetic, not human/);
  });
  it("refuses a grade that is not accept or reshow, and a take graded twice", () => {
    const keep = residual();
    keep.labels[0]!.human = "keep";
    expect(() => checkResidual(keep)).toThrow(/take_0001 human is keep/);
    const twice = residual();
    twice.labels[1]!.take_id = "take_0001";
    expect(() => checkResidual(twice)).toThrow(/take_0001 is graded twice/);
  });
  it("refuses a count or agreement rate the labels do not give", () => {
    expect(() => checkResidual({ ...residual(), n: 3 })).toThrow(/n is 3 for 2 labels/);
    expect(() => checkResidual({ ...residual(), fused_agreement: 0 })).toThrow(/fused_agreement is 0, but the labels give 0.5/);
    expect(() => checkResidual({ ...residual(), labels: [] })).toThrow(/no per-take labels/);
  });
  it("refuses a graded take whose fused decision is not the one grades.json shows", () => {
    const takes = new Map([["take_0001", { grades: { fusion: { final: { decision: "accept" } } } as unknown as Grades }]]);
    expect(() => checkResidualAgainstTakes(checkResidual(residual()), takes)).toThrow(
      /take_0001 fused_judge is reshow, but grades.json decided accept/,
    );
    takes.get("take_0001")!.grades.fusion.final.decision = "reshow";
    expect(() => checkResidualAgainstTakes(checkResidual(residual()), takes)).not.toThrow();
  });
});

describe("outside grade copy", () => {
  it("shows each graded take's grade and both judges from the report, and nothing for an ungraded take", () => {
    const r = checkResidual(residual());
    expect(outsideView(r, "take_0001")).toEqual({
      grader: "accept",
      judges: [
        { judge: "fused", grade: "reshow", agrees: false },
        { judge: "tracking", grade: "accept", agrees: true },
      ],
    });
    expect(outsideView(r, "take_0003")).toBeNull();
    expect(gradeWord("accept")).toBe("Accept");
    expect(gradeWord("reshow")).toBe("Re-show");
  });
  it("follows the report when a grade in it changes", () => {
    const changed = residual();
    changed.labels[0]!.human = "reshow";
    const view = outsideView(checkResidual(rerate(changed)), "take_0001")!;
    expect(view.grader).toBe("reshow");
    expect(view.judges.map((j) => j.agrees)).toEqual([true, false]);
  });
  it("counts each judge's matches from the labels and explains an undefined kappa from them", () => {
    const [counts, verdict] = residualSentences(checkResidual(residual()));
    expect(counts).toBe("Showhand's decision matched an outside grader on 1 of 2 takes, and tracking error alone matched on 2 of 2.");
    expect(verdict).toEqual([
      "The comparison was pre-registered before any grade arrived, and under its own rule the result is ",
      { code: "evaluation_invalid" },
      ": the grader and tracking error alone accepted every take, so Cohen's kappa for tracking error alone is undefined and the rule gives no verdict on which judge is closer to a human.",
    ]);
  });
  it("changes the counts and the reason when the report changes", () => {
    const changed = residual();
    changed.labels[1]!.tracking_alone = "reshow";
    const [counts, verdict] = residualSentences(checkResidual(rerate(changed)));
    expect(counts).toMatch(/tracking error alone matched on 1 of 2\.$/);
    // The labels no longer explain the undefined kappa, so the report's own reason prints.
    expect(verdict.at(-1)).toBe(": the report's own reason.");
    const evaluated = residualSentences(checkResidual({ ...residual(), status: "evaluated", tracking_kappa: 0.2 }))[1];
    expect(evaluated).toEqual([expect.any(String), { code: "evaluated" }, "."]);
  });
});

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
  it("refuses a grades file without its recorded run times", () => {
    const g = grades();
    delete g.runtime.gem_x_offline_s;
    expect(() => checkGrades(g, "take_0001")).toThrow(/runtime.gem_x_offline_s/);
    const { runtime: _dropped, ...none } = grades();
    expect(() => checkGrades(none, "take_0001")).toThrow(/no recorded run times/);
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
  it("reads the reason code back out of a guarded re-show reason", () => {
    expect(windowReason("tracking_p95_abs_error_rad in cited evidence")).toBe("worst joint error");
    expect(windowReason("something the guard never wrote")).toBe("something the guard never wrote");
  });
  it("writes the answer line from the final decision, never from its own copy", () => {
    const nb = " ";
    expect(
      callLine({ decision: "reshow", reshow_windows: [{ start_s: 0, end_s: 1, reason: "out_of_balance in cited evidence" }] }),
    ).toBe(`Re-show 0 to 1${nb}s: out of balance`);
    expect(
      callLine({
        decision: "reshow",
        reshow_windows: [
          { start_s: 1, end_s: 2, reason: "tracking_p95_abs_error_rad in cited evidence" },
          { start_s: 4, end_s: 5, reason: "upper_body_pose in cited evidence" },
        ],
      }),
    ).toBe(`Re-show 1 to 2${nb}s (worst joint error) and 4 to 5${nb}s (upper body pose)`);
    expect(callLine({ decision: "accept", reshow_windows: [] })).toBe("Accepted. No second goes back.");
    expect(callLine({ decision: "reshow", reshow_windows: [] })).toMatch(/whole take/);
  });
  it("lists failing seconds the decision left out, counting Cosmos but not Super VL", () => {
    const g = grades();
    const fail = { ...g.seconds[0]!.rules, pass: false, reason_codes: ["out_of_balance"] };
    const noMatch = { match: false, status: "valid", reason_codes: ["orientation"], summary: "s" };
    const rows = [
      { start_s: 0, end_s: 1, rules: fail, cosmos: null, supervl: null },
      { start_s: 1, end_s: 2, rules: g.seconds[0]!.rules, cosmos: noMatch, supervl: null },
      { start_s: 2, end_s: 3, rules: g.seconds[0]!.rules, cosmos: null, supervl: noMatch },
    ];
    const left = unsentFailingSeconds(rows, [{ start_s: 0, end_s: 1, reason: "out_of_balance in cited evidence" }]);
    expect(left.map((r) => r.start_s)).toEqual([1]);
    expect(unsentSentence(left)).toMatch(/1 to 2.s also failed and is not in the list/);
    expect(unsentSentence([])).toBe("");
  });
  it("splits the answer so each window's seconds can be a button, with the same text", () => {
    const final = {
      decision: "reshow",
      reshow_windows: [
        { start_s: 1, end_s: 2, reason: "tracking_p95_abs_error_rad in cited evidence" },
        { start_s: 4, end_s: 5, reason: "upper_body_pose in cited evidence" },
      ],
    };
    const parts = callParts(final);
    expect(parts.filter((p) => typeof p !== "string")).toEqual(final.reshow_windows);
    expect(callLine(final)).toBe("Re-show 1 to 2 s (worst joint error) and 4 to 5 s (upper body pose)");
  });
  it("prints the fusion call's time and cost from the record", () => {
    const attempt = { attempt: 1, guard: "refused", guard_error: null, proposal: null, latency_s: 0.897992 };
    expect(
      fusionCostLine({ attempts: [attempt, { ...attempt, attempt: 2, latency_s: 0.806705 }], cost_usd: 0.00030144 }),
    ).toBe("Nemotron 3.5 Lightning: 0.90 s and 0.81 s, $0.00030");
    expect(fusionCostLine({ attempts: [{ ...attempt, latency_s: null }], cost_usd: 0.0001 })).toBe(
      "Nemotron 3.5 Lightning: $0.00010",
    );
  });
  it("says in one sentence what the guard did with Nemotron's answers", () => {
    const accept = { decision: "accept", reshow_windows: [] };
    const caught = {
      decided_by: "nemotron",
      attempts: [
        { attempt: 1, guard: "refused", guard_error: "accept contradicts mandatory negative evidence", proposal: accept, latency_s: 0.9 },
        { attempt: 2, guard: "passed", guard_error: null, proposal: accept, latency_s: 0.7 },
      ],
    };
    expect(guardCaught(caught)).toBe(true);
    expect(catchLine(caught)).toBe(
      'Nemotron first answered accept, the guard refused it ("accept contradicts mandatory negative evidence"), and the retry passed.',
    );
    const fellBack = {
      decided_by: "deterministic_fallback",
      attempts: [
        { attempt: 1, guard: "refused", guard_error: "e", proposal: accept, latency_s: 1 },
        { attempt: 2, guard: "refused", guard_error: "e", proposal: accept, latency_s: 1 },
      ],
    };
    expect(guardCaught(fellBack)).toBe(false);
    expect(catchLine(fellBack)).toMatch(/^The guard refused both of Nemotron's answers \("e"\), so Showhand re-showed/);
    const first = { decided_by: "nemotron", attempts: [{ ...caught.attempts[1]!, attempt: 1 }] };
    expect(guardCaught(first)).toBe(false);
    expect(catchLine(first)).toBe("The guard passed Nemotron's first answer.");
  });
  it("explains each fusion outcome the grader writes", () => {
    expect(decidedByText("deterministic_fallback", "fallback_after_guard_refusals")).toMatch(/fell back/);
    // The fallback reads the measured seconds and the Cosmos verdicts only (src/showhand/fusion.py).
    expect(decidedByText("deterministic_fallback", "fallback_after_guard_refusals")).toMatch(/Cosmos Reason1/);
    expect(decidedByText("deterministic_fallback", "fallback_after_guard_refusals")).not.toMatch(/visual evidence/);
    expect(decidedByText("nemotron", "passed_after_retry")).toMatch(/retry/);
    expect(decidedByText("nemotron", "passed_first")).toMatch(/first answer/);
  });
});
