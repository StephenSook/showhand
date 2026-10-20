import "./styles.css";
import { loadIndex, loadTake, type Grades, type ReshowWindow, type SecondRow, type Take, type Verdict } from "./data";
import { TimerClock, VideoClock, videoReady, type Clock } from "./clock";
import { RobotScene, type SceneColors } from "./scene";
import { UNIT_SPACE, frameAt, formatClock, replayDuration, sameWindows, secondAt, span, spans } from "./time";
import {
  COSMOS_RULE,
  METRICS,
  SUPERVL_RULE,
  callParts,
  catchLine,
  decidedByText,
  fusionCostLine,
  guardCaught,
  limitText,
  reasonList,
  unsentFailingSeconds,
  unsentSentence,
  valueText,
  windowReason,
} from "./copy";

const BASE = "/replay";

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function byId<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`page is missing #${id}`);
  return node as T;
}

function sceneColors(): SceneColors {
  const css = getComputedStyle(document.documentElement);
  const read = (name: string) => css.getPropertyValue(name).trim();
  return { stage: read("--stage"), grid: read("--grid"), pass: read("--pass"), fail: read("--fail") };
}

function pct(value: number, total: number): string {
  return `${((value / total) * 100).toFixed(3)}%`;
}

function takeNumber(id: string): string {
  return id.replace(/^take_/, "");
}

function verdictMark(verdict: Verdict | null): { cls: string; glyph: string; text: string } {
  if (verdict === null || verdict.match === null || verdict.status !== "valid") {
    return { cls: "none", glyph: "?", text: "no valid answer" };
  }
  return verdict.match
    ? { cls: "pass", glyph: "✓", text: "match" }
    : { cls: "fail", glyph: "✗", text: "no match" };
}

// ---- state ----
const takes = new Map<string, Take>();
let take: Take;
let clock: Clock;
let robot: RobotScene;
let duration = 1;
let shownSecond = -1;
let rate = 1;
let selection = 0;
const video = byId<HTMLVideoElement>("video");
const playButton = byId<HTMLButtonElement>("play");
const scrub = byId<HTMLInputElement>("scrub");
const clockText = byId<HTMLElement>("clock");
const timeline = byId<HTMLElement>("timeline");
let playhead: HTMLElement | null = null;
let ruleCells: HTMLElement[][] = [];

function showError(message: string): void {
  const box = byId<HTMLElement>("error");
  box.textContent = `The replay could not load. ${message}`;
  box.hidden = false;
  document.body.dataset.ready = "error";
}

// ---- take switcher ----
function renderTakes(order: string[]): void {
  const nav = byId<HTMLElement>("takes");
  nav.replaceChildren(
    ...order.map((id) => {
      const t = takes.get(id)!;
      const windows = t.grades.fusion.final.reshow_windows;
      const summary =
        t.grades.fusion.final.decision === "accept" ? "Accepted" : `Re-show ${spans(windows)}`;
      const button = el(
        "button",
        { class: "take", type: "button", "data-take": id, "aria-pressed": "false" },
        el("strong", {}, `Take ${takeNumber(id)}`),
        el("span", {}, summary),
      );
      button.addEventListener("click", () => void selectTake(id, true));
      return button;
    }),
  );
}

// ---- timeline ----
function lane(label: string, short: string, track: HTMLElement, extra = ""): HTMLElement {
  return el(
    "div",
    { class: `lane ${extra}`.trim() },
    el("div", { class: "lane-label" }, el("span", { class: "long" }, ...labelParts(label)), el("span", { class: "short" }, short)),
    track,
  );
}

function labelParts(label: string): (Node | string)[] {
  const [head, ...rest] = label.split("\n");
  return rest.length ? [el("b", {}, head!), rest.join(" ")] : [el("b", {}, head!)];
}

function cellButton(row: SecondRow, index: number, total: number, cls: string, glyph: string, text: string, lane: string): HTMLElement {
  const button = el(
    "button",
    {
      class: `cell ${cls}`,
      type: "button",
      style: `left: calc(${pct(row.start_s, total)} + 1px); width: calc(${pct(row.end_s - row.start_s, total)} - 2px)`,
      "aria-label": `${lane}, ${span(row.start_s, row.end_s)}: ${text}`,
      "data-second": String(index),
    },
    el("span", { "aria-hidden": "true" }, glyph),
  );
  button.addEventListener("click", () => {
    clock.pause();
    clock.seek(row.start_s + 0.001);
    tick(true);
  });
  return button;
}

function renderTimeline(t: Take): void {
  const g = t.grades;
  const total = duration;
  const axis = el("div", { class: "track" });
  for (let s = 0; s <= Math.floor(total + 1e-6); s++) {
    axis.append(el("span", { class: "tick", style: `left: ${pct(s, total)}` }, `${s} s`));
  }

  const rules = el("div", { class: "track" });
  const cosmos = el("div", { class: "track" });
  const supervl = el("div", { class: "track" });
  ruleCells = [];
  g.seconds.forEach((row, i) => {
    const ruleText = row.rules.pass ? "passed" : `failed on ${reasonList(row.rules.reason_codes)}`;
    const c = verdictMark(row.cosmos);
    const v = verdictMark(row.supervl);
    const cells = [
      cellButton(row, i, total, row.rules.pass ? "pass" : "fail", row.rules.pass ? "✓" : "✗", ruleText, "Measured"),
      cellButton(row, i, total, c.cls, c.glyph, c.text, "Cosmos Reason1"),
      cellButton(row, i, total, v.cls, v.glyph, v.text, "Nemotron Super VL"),
    ];
    rules.append(cells[0]!);
    cosmos.append(cells[1]!);
    supervl.append(cells[2]!);
    ruleCells.push(cells);
  });

  const balance = el("div", { class: "track", role: "img", "aria-label": balanceLabel(t) });
  balance.append(el("span", { class: "balance-base" }));
  for (const [start, end] of runs(t.outOfBalance)) {
    const from = start / t.replay.fps;
    const to = Math.min((end + 1) / t.replay.fps, total);
    balance.append(el("span", { class: "balance-run", style: `left: ${pct(from, total)}; width: ${pct(to - from, total)}` }));
  }

  const lanes: HTMLElement[] = [
    lane("Time", "Time", axis, "axis"),
    lane("Measured\nfrom the simulator", "Measured", rules),
    lane("Cosmos Reason1\nvision, counted", "Cosmos", cosmos),
    lane("Super VL\nvision, not counted", "Super VL", supervl),
    el("p", { class: "lane-note", id: "judge-rule" }, COSMOS_RULE, " ", SUPERVL_RULE),
    lane("Balance\nframe by frame", "Balance", balance),
  ];

  g.fusion.attempts.forEach((attempt, i) => {
    const track = el("div", { class: "track" });
    const refused = attempt.guard !== "passed";
    const windows = attempt.proposal?.reshow_windows ?? [];
    const decision = attempt.proposal?.decision ?? "no readable answer";
    if (windows.length === 0) {
      track.append(
        el(
          "span",
          { class: `window ${refused ? "empty" : "proposed"}` },
          decision === "accept" ? `Proposed accept${refused ? ", refused" : ""}` : `${decision}${refused ? ", refused" : ""}`,
        ),
      );
    }
    for (const w of windows) {
      track.append(
        el(
          "span",
          {
            class: `window ${refused ? "refused" : "proposed"}`,
            style: `left: ${pct(w.start_s, total)}; width: ${pct(w.end_s - w.start_s, total)}`,
            title: w.reason,
          },
          refused ? "refused" : "proposed",
        ),
      );
    }
    const label = `Nemotron, try ${attempt.attempt}\n${refused ? "guard refused" : "guard passed"}`;
    lanes.push(lane(label, `Try ${attempt.attempt}`, track, i === 0 ? "lane-group" : ""));
  });

  const final = el("div", { class: "track" });
  const finalWindows = g.fusion.final.reshow_windows;
  if (g.fusion.final.decision === "accept") {
    final.append(el("span", { class: "window proposed", style: "left: 0; right: 0" }, "Accepted"));
  }
  for (const w of finalWindows) {
    final.append(
      el(
        "span",
        { class: "window final", style: `left: ${pct(w.start_s, total)}; width: ${pct(w.end_s - w.start_s, total)}`, title: w.reason },
        "re-show",
      ),
    );
  }
  lanes.push(lane("Decision\nseconds sent back", "Decision", final));

  playhead = el("div", { class: "playhead", "aria-hidden": "true" });
  timeline.replaceChildren(...lanes, playhead);
  timeline.dataset.seconds = String(g.seconds.length);
  timeline.dataset.attempts = String(g.fusion.attempts.length);

  // Clicking anywhere on a track (outside a cell) moves the playhead there.
  timeline.onclick = (event) => {
    const target = event.target as HTMLElement;
    if (target.closest("button")) return;
    const track = target.closest(".track");
    if (!track) return;
    const box = track.getBoundingClientRect();
    clock.seek(((event.clientX - box.left) / box.width) * duration);
    tick(true);
  };
}

function runs(flags: Uint8Array): [number, number][] {
  const out: [number, number][] = [];
  let start = -1;
  flags.forEach((flag, i) => {
    if (flag && start < 0) start = i;
    if (!flag && start >= 0) {
      out.push([start, i - 1]);
      start = -1;
    }
  });
  if (start >= 0) out.push([start, flags.length - 1]);
  return out;
}

function balanceLabel(t: Take): string {
  const count = t.outOfBalance.reduce((sum, f) => sum + f, 0);
  return `Out of balance in ${count} of ${t.outOfBalance.length} frames`;
}

function overallText(g: Grades): string {
  const measured = g.overall.pass
    ? "The whole take passed every measured limit."
    : `The whole take failed on ${reasonList(g.overall.reason_codes)}.`;
  const final = g.fusion.final;
  const decision =
    final.decision === "accept" ? "Showhand accepted it." : `Showhand sent back ${spans(final.reshow_windows)}.`;
  return `${measured} ${decision}`;
}

// ---- the answer above the video, and the same seconds on the seek bar ----
function renderCall(t: Take): void {
  byId<HTMLElement>("call-line").replaceChildren(
    ...callParts(t.grades.fusion.final).map((part) => {
      if (typeof part === "string") return part;
      const button = el(
        "button",
        {
          class: "call-seek",
          type: "button",
          "aria-describedby": "seek-hint",
          "data-start": String(part.start_s),
        },
        span(part.start_s, part.end_s),
      );
      button.addEventListener("click", () => showSeconds(part.start_s));
      return button;
    }),
  );
  const caught = catchLine(t.grades.fusion);
  const line = byId<HTMLElement>("call-catch");
  line.textContent = caught;
  line.hidden = caught === "";
  byId<HTMLElement>("call-cost").textContent = fusionCostLine(t.grades.fusion);
}

// A re-show button moves the recording and the robot to that second. It leaves play or pause as
// it was. If the stage is partly off screen it scrolls into view, without animation when the
// viewer asked for reduced motion.
function showSeconds(start: number): void {
  // Until the take's clock exists (its video is still loading) there is nothing to move.
  if (document.body.dataset.take !== take.id) return;
  clock.seek(start + 0.001);
  tick(true);
  const stage = document.querySelector<HTMLElement>(".stage")!;
  const box = stage.getBoundingClientRect();
  if (box.top < 0 || box.bottom > window.innerHeight) {
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    stage.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "nearest" });
  }
}

function renderSeekRanges(t: Take): void {
  const track = byId<HTMLElement>("seek-track");
  const windows = t.grades.fusion.final.reshow_windows;
  track.replaceChildren(
    ...windows.map((w) => {
      const end = Math.min(w.end_s, duration);
      return el("span", {
        class: "seek-range",
        style: `left: ${pct(w.start_s, duration)}; width: ${pct(Math.max(0, end - w.start_s), duration)}`,
        title: `Re-show ${span(w.start_s, w.end_s)}: ${windowReason(w.reason)}`,
        "data-start": String(w.start_s),
        "data-end": String(w.end_s),
      });
    }),
  );
  track.dataset.ranges = String(windows.length);
}

// ---- where each stage ran, with the times the take records hold ----
function secondsText(value: number): string {
  return `${value.toFixed(1)}${UNIT_SPACE}s`;
}

function usd(value: number): string {
  return `$${value.toFixed(5)}`;
}

function renderRuns(t: Take): void {
  const r = t.grades.runtime;
  byId<HTMLElement>("run-gemx").textContent = secondsText(r.gem_x_offline_s);
  byId<HTMLElement>("run-replay").textContent = secondsText(r.replay_process_wall_s);
  byId<HTMLElement>("run-cosmos").textContent = secondsText(r.cosmos_model_load_s);
  const checks = t.grades.seconds.filter((row) => row.supervl !== null).length;
  byId<HTMLElement>("run-supervl-count").textContent = `${checks} seconds checked`;
  byId<HTMLElement>("run-supervl").textContent = `${secondsText(r.supervl_wall_s)}, ${usd(r.supervl_cost_usd)}`;
}

// ---- detail panels ----
function renderSecond(index: number): void {
  const g = take.grades;
  const row = g.seconds[index]!;
  const panel = byId<HTMLElement>("second");
  const failing = new Set(row.rules.reason_codes);
  const body = el("tbody");
  for (const spec of METRICS) {
    const value = row.rules[spec.field];
    if (typeof value !== "number") continue;
    const over = failing.has(spec.reason);
    body.append(
      el(
        "tr",
        over ? { class: "over" } : {},
        el("td", {}, spec.label),
        el("td", { class: "num" }, valueText(spec, value)),
        el("td", { class: "num" }, limitText(spec, g.cutoffs)),
        el("td", {}, el("span", { class: `mark ${over ? "fail" : "pass"}`, "aria-hidden": "true" }, over ? "✗" : "✓"), over ? "over" : "within"),
      ),
    );
  }
  const judge = (name: string, model: string, verdict: Verdict | null, weight: string) => {
    const mark = verdictMark(verdict);
    const why = verdict && verdict.reason_codes.length ? ` on ${reasonList(verdict.reason_codes)}` : "";
    return el(
      "div",
      { class: "judge" },
      el("h3", {}, el("span", { class: `mark ${mark.cls === "none" ? "fail" : mark.cls}`, "aria-hidden": "true" }, mark.glyph), `${name}: ${mark.text}${why}`),
      el("p", { class: "model" }, `${model}. ${weight}`),
      el("p", { class: "quote" }, verdict?.summary ? `"${verdict.summary}"` : "No summary returned."),
    );
  };
  const reshow = g.fusion.final.reshow_windows.some((w) => row.start_s < w.end_s && w.start_s < row.end_s);
  panel.replaceChildren(
    el("h2", { id: "second-heading" }, `Second ${span(row.start_s, row.end_s).replace(`${UNIT_SPACE}s`, "")}`),
    el(
      "p",
      { class: "status-line" },
      row.rules.pass ? "Every measured value is inside its limit." : `Over the limit on ${reasonList(row.rules.reason_codes)}.`,
      " ",
      reshow ? "This second is in the re-show list." : "This second is not in the re-show list.",
    ),
    el(
      "table",
      {},
      el("caption", { class: "fineprint", style: "text-align:left; caption-side: bottom" }, "Measured on the simulated G1 against the frozen limits in config/thresholds.yaml."),
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Measure"), el("th", { scope: "col" }, "This second"), el("th", { scope: "col" }, "Limit"), el("th", { scope: "col" }, "Result"))),
      body,
    ),
    judge("Cosmos Reason1", g.models.cosmos, row.cosmos, "Counted in the decision."),
    judge("Super VL", g.models.supervl, row.supervl, "A second opinion, not counted in the decision."),
  );
}

function renderFusion(): void {
  const g = take.grades;
  const panel = byId<HTMLElement>("fusion");
  const steps = el("ol", { class: "steps" });
  for (const attempt of g.fusion.attempts) {
    const refused = attempt.guard !== "passed";
    const proposal = attempt.proposal;
    const said =
      proposal === null
        ? "Nemotron's answer could not be read."
        : proposal.decision === "accept"
          ? "Nemotron proposed accepting the take."
          : `Nemotron proposed re-showing ${spans(proposal.reshow_windows)}.`;
    const timing = attempt.latency_s === null ? "" : ` (${attempt.latency_s.toFixed(2)} s)`;
    steps.append(
      el(
        "li",
        { class: refused ? "refused" : "" },
        el("h3", {}, `Try ${attempt.attempt}${timing}`),
        el("p", {}, said),
        el("p", { class: "quote" }, refused ? `The guard refused it: "${attempt.guard_error ?? "no reason recorded"}".` : "The guard passed it."),
      ),
    );
  }
  const final = g.fusion.final;
  const lastProposal = g.fusion.attempts.at(-1)?.proposal;
  const changed =
    g.fusion.decided_by === "deterministic_fallback" &&
    lastProposal !== null &&
    lastProposal !== undefined &&
    !sameWindows(lastProposal.reshow_windows, final.reshow_windows);
  steps.append(
    el(
      "li",
      { class: "final" },
      el("h3", {}, final.decision === "accept" ? "Decision: accept" : `Decision: re-show ${spans(final.reshow_windows)}`),
      el("p", {}, decidedByText(g.fusion.decided_by, g.fusion.status)),
      changed ? el("p", { class: "quote" }, "That is a different list from anything Nemotron proposed.") : "",
      unsentText(g.seconds, final.reshow_windows),
    ),
  );
  panel.replaceChildren(
    el("h2", { id: "fusion-heading" }, "How the decision was made"),
    el(
      "p",
      { class: "status-line" },
      `${g.models.fusion} reads the measured seconds and the Cosmos Reason1 verdicts, then proposes accept or the seconds to re-show. The guard refuses any second it sends back that is not a failing measured or Cosmos second it cited, and refuses accept while the whole take fails a measured limit or Cosmos marked any second as no match.`,
    ),
    steps,
    el("p", { class: "fineprint" }, `Fusion cost ${usd(g.fusion.cost_usd)}. Request ${g.fusion.request_id}.`),
  );
}

function unsentText(seconds: SecondRow[], windows: ReshowWindow[]): HTMLElement | string {
  const sentence = unsentSentence(unsentFailingSeconds(seconds, windows));
  return sentence ? el("p", { class: "quote", id: "unsent" }, sentence) : "";
}

// ---- playback ----
function tick(force = false): void {
  const t = Math.min(clock.time(), duration);
  robot.pose(take, frameAt(t, take.replay.fps, take.replay.frames));
  robot.follow();
  const track = timeline.querySelector<HTMLElement>(".track");
  if (playhead && track) playhead.style.left = `${track.offsetLeft + track.offsetWidth * (t / duration)}px`;
  clockText.replaceChildren(formatClock(t), el("small", {}, ` / ${formatClock(duration)}`));
  if (document.activeElement !== scrub) scrub.value = String(t);
  const second = secondAt(t, take.grades.seconds);
  if (force || second !== shownSecond) {
    ruleCells[shownSecond]?.forEach((cell) => cell.classList.remove("current"));
    ruleCells[second]?.forEach((cell) => cell.classList.add("current"));
    shownSecond = second;
    renderSecond(second);
  }
  const playing = clock.playing();
  playButton.textContent = playing ? "Pause" : "Play";
  playButton.setAttribute("aria-pressed", String(playing));
}

function loop(): void {
  tick();
  robot.render();
  requestAnimationFrame(loop);
}

async function selectTake(id: string, userAction: boolean): Promise<void> {
  const next = takes.get(id);
  if (!next) throw new Error(`no take ${id}`);
  const wasPlaying = clock?.playing() ?? false;
  clock?.pause();
  take = next;
  document.querySelectorAll<HTMLButtonElement>(".take").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.take === id)));
  if (userAction) history.replaceState(null, "", `?take=${id}`);
  robot.bind(take);
  // The answer does not depend on the video, so it changes the moment the take does.
  renderCall(take);
  renderRuns(take);

  const replaySeconds = replayDuration(take.replay.fps, take.replay.frames);
  const mine = ++selection;
  const hasVideo = await videoReady(video, `${BASE}/${id}/source.mp4`);
  if (mine !== selection) return;
  byId<HTMLElement>("missing-video").hidden = hasVideo;
  if (hasVideo) {
    if (video.videoWidth && video.videoHeight) {
      video.parentElement!.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
    }
    duration = Math.min(replaySeconds, video.duration || replaySeconds);
    clock = new VideoClock(video, duration);
  } else {
    duration = replaySeconds;
    clock = new TimerClock(duration);
  }
  clock.setRate(rate);
  document.body.dataset.clock = clock.kind;
  document.body.dataset.take = id;
  scrub.max = String(duration);
  scrub.step = String(1 / take.replay.fps);
  shownSecond = -1;
  renderSeekRanges(take);
  renderTimeline(take);
  renderFusion();
  byId<HTMLElement>("verdict").textContent = overallText(take.grades);
  clock.seek(0);
  tick(true);
  if (wasPlaying || (!userAction && !matchMedia("(prefers-reduced-motion: reduce)").matches)) clock.play();
}

function wireControls(): void {
  playButton.addEventListener("click", () => {
    if (clock.playing()) clock.pause();
    else clock.play();
    tick();
  });
  scrub.addEventListener("input", () => {
    clock.pause();
    clock.seek(Number(scrub.value));
    tick();
  });
  document.querySelectorAll<HTMLButtonElement>(".speeds button").forEach((button) => {
    button.addEventListener("click", () => {
      rate = Number(button.dataset.rate);
      clock.setRate(rate);
      document.querySelectorAll(".speeds button").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
    });
  });
  document.addEventListener("keydown", (event) => {
    const target = event.target as HTMLElement;
    if (event.key !== " " || target.closest("button, input, a, textarea, select")) return;
    event.preventDefault();
    playButton.click();
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => robot.setColors(sceneColors()));
}

async function main(): Promise<void> {
  const index = await loadIndex(BASE, fetch);
  const loaded = await Promise.all(index.map((entry) => loadTake(BASE, entry, fetch)));
  for (const t of loaded) takes.set(t.id, t);
  robot = await RobotScene.create(byId<HTMLCanvasElement>("robot"), `${BASE}/g1.glb`, sceneColors());
  renderTakes(index.map((entry) => entry.take));
  wireControls();
  // A ?take= link opens that take. Otherwise open on the first take where the guard refused
  // Nemotron's answer and a retry passed (take_0526 today), falling back to the first take.
  const asked = new URLSearchParams(location.search).get("take");
  const featured = index.find((entry) => guardCaught(takes.get(entry.take)!.grades.fusion)) ?? index[0]!;
  await selectTake(asked && takes.has(asked) ? asked : featured.take, false);
  document.body.dataset.ready = "true";
  requestAnimationFrame(loop);
}

main().catch((error: unknown) => showError(error instanceof Error ? error.message : String(error)));
