// Plain-language names for the codes in grades.json. An unknown code still prints (with its
// underscores turned into spaces) so a new code from the grader never disappears from the page.

import type { ReshowWindow, RuleRow, SecondRow } from "./data";
import { span, spans } from "./time";

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
export function callLine(final: { decision: string; reshow_windows: ReshowWindow[] }): string {
  if (final.decision === "accept") return "Accepted. No second goes back.";
  const windows = final.reshow_windows;
  if (windows.length === 0) return "Re-show the whole take. No single second failed on its own.";
  if (windows.length === 1) {
    const w = windows[0]!;
    return `Re-show ${span(w.start_s, w.end_s)}: ${windowReason(w.reason)}`;
  }
  const parts = windows.map((w) => `${span(w.start_s, w.end_s)} (${windowReason(w.reason)})`);
  return `Re-show ${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
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
