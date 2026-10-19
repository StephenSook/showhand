// Shapes of the files tools/replay_glb.py and tools/replay_grades.py write into public/replay,
// plus the checks that refuse a file that does not match. A mismatched export should stop the
// page with a named error, never draw a robot that is out of step with its grades.

export interface GeomRef {
  node: string;
  body: string;
}

export interface FrameTime {
  frame: number;
  sim_time_s: number;
  out_of_balance: string;
  fall_event: string;
}

export interface ReplayManifest {
  schema_version: 1;
  take: string;
  fps: number;
  frames: number;
  geoms: GeomRef[];
  frame_layout: string;
  frame_times: FrameTime[];
  frames_sha256: string;
}

export interface Verdict {
  match: boolean | null;
  status: string;
  reason_codes: string[];
  summary: string;
}

export interface RuleRow {
  pass: boolean;
  reason_codes: string[];
  tracking_mean_abs_error_rad: number;
  tracking_p95_abs_error_rad: number;
  root_tilt_max_deg: number;
  root_height_min_m: number;
  foot_slip_max_m_s: number;
  foot_slip_seconds: number;
  out_of_balance_seconds: number;
  falls: number;
}

export interface SecondRow {
  start_s: number;
  end_s: number;
  rules: RuleRow;
  cosmos: Verdict | null;
  supervl: Verdict | null;
}

export interface ReshowWindow {
  start_s: number;
  end_s: number;
  reason: string;
}

export interface Attempt {
  attempt: number;
  guard: string;
  guard_error: string | null;
  proposal: { decision: string; reshow_windows: ReshowWindow[] } | null;
  latency_s: number | null;
}

export interface Grades {
  schema_version: 1;
  take: string;
  duration_s: number;
  overall: { pass: boolean; reason_codes: string[] };
  cutoffs: Record<string, number>;
  models: { cosmos: string; supervl: string; fusion: string };
  seconds: SecondRow[];
  fusion: {
    decided_by: string;
    status: string;
    request_id: string;
    cost_usd: number;
    attempts: Attempt[];
    final: { decision: string; evidence_refs: string[]; reshow_windows: ReshowWindow[] };
  };
}

export interface TakeIndexEntry {
  take: string;
  label: string;
  decision: string;
}

export interface Take {
  id: string;
  label: string;
  replay: ReplayManifest;
  grades: Grades;
  frames: Float32Array;
  outOfBalance: Uint8Array;
}

export const FLOATS_PER_GEOM = 7;

function fail(file: string, why: string): never {
  throw new Error(`${file}: ${why}`);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function finite(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function checkIndex(value: unknown): TakeIndexEntry[] {
  const file = "index.json";
  if (!isRecord(value) || value.schema_version !== 1) fail(file, "expected schema_version 1");
  const takes = value.takes;
  if (!Array.isArray(takes) || takes.length === 0) fail(file, "lists no takes");
  return takes.map((entry, i) => {
    if (!isRecord(entry) || typeof entry.take !== "string" || !/^take_\d+$/.test(entry.take)) {
      fail(file, `entry ${i} has no take id`);
    }
    return {
      take: entry.take,
      label: typeof entry.label === "string" ? entry.label : entry.take,
      decision: typeof entry.decision === "string" ? entry.decision : "unknown",
    };
  });
}

export function checkReplay(value: unknown, take: string): ReplayManifest {
  const file = `${take}/replay.json`;
  if (!isRecord(value) || value.schema_version !== 1) fail(file, "expected schema_version 1");
  if (value.take !== take) fail(file, `names take ${String(value.take)}`);
  if (!finite(value.fps) || value.fps <= 0) fail(file, "fps must be a positive number");
  if (!Number.isInteger(value.frames) || (value.frames as number) < 2) {
    fail(file, "needs at least two frames");
  }
  const geoms = value.geoms;
  if (!Array.isArray(geoms) || geoms.length === 0) fail(file, "lists no geoms");
  for (const [i, geom] of geoms.entries()) {
    if (!isRecord(geom) || typeof geom.node !== "string" || typeof geom.body !== "string") {
      fail(file, `geom ${i} needs node and body names`);
    }
  }
  const times = value.frame_times;
  if (!Array.isArray(times) || times.length !== value.frames) {
    fail(file, `frame_times has ${Array.isArray(times) ? times.length : 0} rows for ${String(value.frames)} frames`);
  }
  return value as unknown as ReplayManifest;
}

export function checkGrades(value: unknown, take: string): Grades {
  const file = `${take}/grades.json`;
  if (!isRecord(value) || value.schema_version !== 1) fail(file, "expected schema_version 1");
  if (value.take !== take) fail(file, `names take ${String(value.take)}`);
  if (!finite(value.duration_s) || value.duration_s <= 0) fail(file, "duration_s must be positive");
  const seconds = value.seconds;
  if (!Array.isArray(seconds) || seconds.length === 0) fail(file, "has no per-second rows");
  let previousEnd = 0;
  for (const [i, row] of seconds.entries()) {
    if (!isRecord(row) || !finite(row.start_s) || !finite(row.end_s) || !isRecord(row.rules)) {
      fail(file, `second ${i} is missing its window or rules`);
    }
    if (Math.abs(row.start_s - previousEnd) > 1e-6 || row.end_s <= row.start_s) {
      fail(file, `second ${i} does not continue from ${previousEnd}`);
    }
    previousEnd = row.end_s;
  }
  if (!isRecord(value.cutoffs)) fail(file, "has no cutoffs");
  const fusion = value.fusion;
  if (!isRecord(fusion) || !Array.isArray(fusion.attempts) || !isRecord(fusion.final)) {
    fail(file, "has no fusion record");
  }
  const windows = fusion.final.reshow_windows;
  if (!Array.isArray(windows)) fail(file, "final decision has no re-show list");
  for (const window of windows) {
    if (!isRecord(window) || !finite(window.start_s) || !finite(window.end_s)) {
      fail(file, "a re-show window has no start or end");
    }
    if (window.start_s < 0 || window.end_s > previousEnd + 1e-6 || window.end_s <= window.start_s) {
      fail(file, `re-show window ${window.start_s} to ${window.end_s} is outside the take`);
    }
  }
  return value as unknown as Grades;
}

export function checkFrames(buffer: ArrayBuffer, replay: ReplayManifest): Float32Array {
  const file = `${replay.take}/frames.bin`;
  const expected = replay.frames * replay.geoms.length * FLOATS_PER_GEOM * 4;
  if (buffer.byteLength !== expected) {
    fail(file, `has ${buffer.byteLength} bytes, expected ${expected}`);
  }
  const frames = new Float32Array(buffer);
  for (let i = 0; i < frames.length; i++) {
    if (!Number.isFinite(frames[i])) fail(file, `value ${i} is not a finite number`);
  }
  return frames;
}

export function outOfBalanceFlags(replay: ReplayManifest): Uint8Array {
  return Uint8Array.from(replay.frame_times, (row) => (row.out_of_balance === "1" ? 1 : 0));
}

type Fetcher = (url: string) => Promise<Response>;

async function fetchOk(fetcher: Fetcher, url: string): Promise<Response> {
  const response = await fetcher(url);
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response;
}

export async function loadIndex(base: string, fetcher: Fetcher): Promise<TakeIndexEntry[]> {
  return checkIndex(await (await fetchOk(fetcher, `${base}/index.json`)).json());
}

export async function loadTake(base: string, entry: TakeIndexEntry, fetcher: Fetcher): Promise<Take> {
  const id = entry.take;
  const [replayResponse, gradesResponse, framesResponse] = await Promise.all([
    fetchOk(fetcher, `${base}/${id}/replay.json`),
    fetchOk(fetcher, `${base}/${id}/grades.json`),
    fetchOk(fetcher, `${base}/${id}/frames.bin`),
  ]);
  const replay = checkReplay(await replayResponse.json(), id);
  const grades = checkGrades(await gradesResponse.json(), id);
  const frames = checkFrames(await framesResponse.arrayBuffer(), replay);
  return { id, label: entry.label, replay, grades, frames, outOfBalance: outOfBalanceFlags(replay) };
}
