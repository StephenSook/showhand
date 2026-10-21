// Plain-language names for the codes in grades.json. An unknown code still prints (with its
// underscores turned into spaces) so a new code from the grader never disappears from the page.

import type { Attempt, Grade, Grades, Residual, ReshowWindow, RuleRow, SecondRow } from "./data";
import { UNIT_SPACE, span, spans } from "./time";

const REASONS: Record<string, string> = {
  tracking_mean_abs_error_rad: "mean joint error",
  tracking_p95_abs_error_rad: "worst joint error",
  root_height_m: "pelvis too low",
  root_tilt_deg: "body tilt",
  foot_slip: "foot slip",
  out_of_balance: "out of balance",
  fall: "fall",
  upper_body_pose: "upper body pose",
  lower_body_pose: "lower body pose",
  orientation: "facing direction",
};

export function reasonLabel(code: string): string {
  return REASONS[code] ?? code.replaceAll("_", " ");
}

export function reasonList(codes: string[]): string {
  const labels = codes.map(reasonLabel);
  if (labels.length === 0) return "";
  if (labels.length === 1) return labels[0]!;
  return `${labels.slice(0, -1).join(", ")} and ${labels[labels.length - 1]}`;
}

export interface MetricSpec {
  field: keyof RuleRow;
  label: string;
  unit: string;
  digits: number;
  cutoff: string | null;
  bound: "max" | "min" | "zero";
  reason: string;
}

// Each row names the cutoff key in grades.json, so the page never carries its own copy of a limit.
export const METRICS: MetricSpec[] = [
  { field: "tracking_mean_abs_error_rad", label: "Mean joint error", unit: "rad", digits: 3, cutoff: "tracking_mean_abs_error_rad", bound: "max", reason: "tracking_mean_abs_error_rad" },
  { field: "tracking_p95_abs_error_rad", label: "Worst joint error (95th percentile)", unit: "rad", digits: 3, cutoff: "tracking_p95_abs_error_rad", bound: "max", reason: "tracking_p95_abs_error_rad" },
  { field: "root_tilt_max_deg", label: "Peak body tilt", unit: "°", digits: 1, cutoff: "root_tilt_max_deg", bound: "max", reason: "root_tilt_deg" },
  { field: "root_height_min_m", label: "Lowest pelvis height", unit: "m", digits: 2, cutoff: "root_height_min_m", bound: "min", reason: "root_height_m" },
  { field: "foot_slip_seconds", label: "Time a planted foot slid", unit: "s", digits: 2, cutoff: "foot_slip_seconds", bound: "max", reason: "foot_slip" },
  { field: "out_of_balance_seconds", label: "Time out of balance", unit: "s", digits: 2, cutoff: "out_of_balance_seconds", bound: "max", reason: "out_of_balance" },
  { field: "falls", label: "Falls", unit: "", digits: 0, cutoff: null, bound: "zero", reason: "fall" },
];

export function limitText(spec: MetricSpec, cutoffs: Record<string, number>): string {
  if (spec.bound === "zero") return "none allowed";
  const value = spec.cutoff === null ? undefined : cutoffs[spec.cutoff];
  if (value === undefined) return "no limit recorded";
  const unit = spec.unit === "°" ? "°" : ` ${spec.unit}`;
  return `${spec.bound === "max" ? "at most" : "at least"} ${value}${unit}`;
}

export function valueText(spec: MetricSpec, value: number): string {
  const unit = spec.unit === "" ? "" : spec.unit === "°" ? "°" : ` ${spec.unit}`;
  return `${value.toFixed(spec.digits)}${unit}`;
}

// The guard only passes a re-show reason written as "<reason_code> in cited evidence", so the
// code is read back out of it. Anything else prints as the record has it.
export function windowReason(reason: string): string {
  const match = /^(\S+) in cited evidence$/.exec(reason);
  return match ? reasonLabel(match[1]!) : reason;
}

// The one-line answer above the video: which seconds go back, and why, from the final decision.
// As parts, so the page can make each window's seconds a button; callLine is the same text.
export type CallPart = string | ReshowWindow;

export function callParts(final: { decision: string; reshow_windows: ReshowWindow[] }): CallPart[] {
  if (final.decision === "accept") return ["Accepted. No second goes back."];
  const windows = final.reshow_windows;
  if (windows.length === 0) return ["Re-show the whole take. No single second failed on its own."];
  if (windows.length === 1) return ["Re-show ", windows[0]!, `: ${windowReason(windows[0]!.reason)}`];
  const parts: CallPart[] = ["Re-show "];
  windows.forEach((w, i) => {
    if (i > 0) parts.push(i === windows.length - 1 ? " and " : ", ");
    parts.push(w, ` (${windowReason(w.reason)})`);
  });
  return parts;
}

export function callLine(final: { decision: string; reshow_windows: ReshowWindow[] }): string {
  return callParts(final)
    .map((part) => (typeof part === "string" ? part : span(part.start_s, part.end_s)))
    .join("");
}

// The fusion call's own time and cost, from the attempts and cost in fusion.json.
export function fusionCostLine(fusion: Pick<Grades["fusion"], "attempts" | "cost_usd">): string {
  const times = fusion.attempts
    .map((a) => a.latency_s)
    .filter((t): t is number => t !== null)
    .map((t) => `${t.toFixed(2)}${UNIT_SPACE}s`);
  const timing = times.length ? `${times.length === 2 ? times.join(" and ") : times.join(", ")}, ` : "";
  return `Nemotron 3.5 Lightning: ${timing}$${fusion.cost_usd.toFixed(5)}`;
}

// How the two vision models are weighed, as src/showhand/fusion.py and guard.py do it. Fusion
// gets the measured seconds and the Cosmos Reason1 verdicts (`showhand fusion --visual`). The
// Super VL verdicts come from tools/supervl_judge.py, which nothing in the decision reads.
export const COSMOS_RULE =
  "Cosmos Reason1 counts: a second it marks as no match can be sent back, and any no match blocks an accept.";
export const SUPERVL_RULE =
  "Super VL does not count: it answered the same question on the same frames as a second opinion, and Nemotron, the guard and the fallback never read it.";

// Seconds the decision's own evidence failed (a measured limit, or a Cosmos no match) that are
// not in the re-show list. The guard checks each second sent back, not that every one is.
export function unsentFailingSeconds(seconds: SecondRow[], windows: ReshowWindow[]): SecondRow[] {
  return seconds.filter(
    (row) =>
      (!row.rules.pass || row.cosmos?.match === false) &&
      !windows.some((w) => row.start_s < w.end_s && w.start_s < row.end_s),
  );
}

export function unsentSentence(rows: SecondRow[]): string {
  if (rows.length === 0) return "";
  const verb = rows.length === 1 ? "is" : "are";
  return `The guard checks that each second sent back is backed by failing evidence, not that every failing second is sent back: ${spans(rows)} also failed and ${verb} not in the list.`;
}

type FusionRecord = Pick<Grades["fusion"], "decided_by" | "attempts">;

function firstAnswer(attempt: Attempt): string {
  const proposal = attempt.proposal;
  if (proposal === null) return "Nemotron's first answer could not be read";
  if (proposal.decision === "accept") return "Nemotron first answered accept";
  return `Nemotron first proposed re-showing ${spans(proposal.reshow_windows)}`;
}

// A take where the guard refused an answer and a later try passed: the loop catching the model.
export function guardCaught(fusion: FusionRecord): boolean {
  const passed = fusion.attempts.findIndex((a) => a.guard === "passed");
  return fusion.decided_by === "nemotron" && passed > 0 && fusion.attempts[0]!.guard !== "passed";
}

// One sentence, under the answer, on what the guard did with Nemotron's answers.
export function catchLine(fusion: FusionRecord): string {
  const attempts = fusion.attempts;
  if (attempts.length === 0) return "";
  const first = attempts[0]!;
  if (guardCaught(fusion)) {
    const passed = attempts.find((a) => a.guard === "passed")!;
    const retry = passed.attempt === 2 ? "the retry" : `try ${passed.attempt}`;
    return `${firstAnswer(first)}, the guard refused it ("${first.guard_error ?? "no reason recorded"}"), and ${retry} passed.`;
  }
  if (fusion.decided_by === "deterministic_fallback") {
    const errors = [...new Set(attempts.map((a) => a.guard_error ?? "no reason recorded"))];
    const count = attempts.length === 2 ? "both" : `all ${attempts.length}`;
    return `The guard refused ${count} of Nemotron's answers ("${errors.join('"; "')}"), so Showhand re-showed every second that failed a measured limit or that Cosmos Reason1 marked as no match.`;
  }
  if (first.guard === "passed") return "The guard passed Nemotron's first answer.";
  return "";
}

// ---- the outside human grade, from residual.json (results/residual/report.json) ----

export function gradeWord(grade: Grade): string {
  return grade === "accept" ? "Accept" : "Re-show";
}

export interface OutsideJudge {
  judge: "fused" | "tracking";
  grade: Grade;
  agrees: boolean;
}

export interface OutsideView {
  grader: Grade;
  judges: OutsideJudge[];
}

// One take against the outside grader: their grade, then Showhand's decision and the tracking-only
// decision, each with whether it matches. Null for a take the grader did not grade.
export function outsideView(residual: Residual, takeId: string): OutsideView | null {
  const label = residual.labels.find((row) => row.take_id === takeId);
  if (!label) return null;
  return {
    grader: label.human,
    judges: [
      { judge: "fused", grade: label.fused_judge, agrees: label.fused_judge === label.human },
      { judge: "tracking", grade: label.tracking_alone, agrees: label.tracking_alone === label.human },
    ],
  };
}

// Text with the report's own status word set apart, so the page can print it as code.
export type ReportPart = string | { code: string };

const JUDGE_NAMES = { fused: "Showhand's decision", tracking: "tracking error alone" } as const;

function graded(grade: Grade): string {
  return grade === "accept" ? "accepted" : "sent back";
}

// Why a judge's kappa is undefined, read off the labels: kappa has no value when the grader and
// that judge each gave every take one and the same grade. Null when the labels do not show that.
function sameEverywhere(residual: Residual, field: "fused_judge" | "tracking_alone"): Grade | null {
  const first = residual.labels[0]!.human;
  return residual.labels.every((row) => row.human === first && row[field] === first) ? first : null;
}

// The agreement counts and the pre-registered result in two sentences, each built from the report.
export function residualSentences(residual: Residual): [string, ReportPart[]] {
  const n = residual.labels.length;
  const matched = (field: "fused_judge" | "tracking_alone") =>
    residual.labels.filter((row) => row[field] === row.human).length;
  const counts = `Showhand's decision matched an outside grader on ${matched("fused_judge")} of ${n} ${
    n === 1 ? "take" : "takes"
  }, and tracking error alone matched on ${matched("tracking_alone")} of ${n}.`;
  const lead = "The comparison was pre-registered before any grade arrived, and under its own rule the result is ";
  if (residual.status !== "evaluation_invalid") {
    return [counts, [lead, { code: residual.status }, "."]];
  }
  const undefinedJudges = (
    [
      ["fused", "fused_judge", residual.fused_kappa],
      ["tracking", "tracking_alone", residual.tracking_kappa],
    ] as const
  ).filter(([, , value]) => value === null);
  const reasons = undefinedJudges.map(([judge, field]) => {
    const grade = sameEverywhere(residual, field);
    return grade === null ? null : `the grader and ${JUDGE_NAMES[judge]} ${graded(grade)} every take`;
  });
  if (undefinedJudges.length === 0 || reasons.some((reason) => reason === null)) {
    // The labels do not explain it, so print the report's own reason.
    return [counts, [lead, { code: residual.status }, residual.why ? `: ${residual.why}.` : "."]];
  }
  const names = undefinedJudges.map(([judge]) => JUDGE_NAMES[judge]).join(" and ");
  return [
    counts,
    [
      lead,
      { code: residual.status },
      `: ${reasons.join(", and ")}, so Cohen's kappa for ${names} is undefined and the rule gives no verdict on which judge is closer to a human.`,
    ],
  ];
}

export function decidedByText(decidedBy: string, status: string): string {
  if (decidedBy === "deterministic_fallback") {
    return "Nemotron never gave an answer the guard accepted, so Showhand fell back to re-showing every second that failed a measured limit or that Cosmos Reason1 marked as no match.";
  }
  if (status === "passed_after_retry") {
    return "Nemotron's retry cited the failing evidence, the guard passed it, and that answer stands.";
  }
  if (status === "passed_first") return "The guard passed Nemotron's first answer.";
  return `Fusion ended with status ${status.replaceAll("_", " ")}.`;
}
