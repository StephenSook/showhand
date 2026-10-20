// The committed replay files must agree with each other and with the take records they came
// from. A re-export that changes one file and not another fails here, not on the deployed page.

import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { checkFrames, checkGrades, checkIndex, checkReplay, FLOATS_PER_GEOM } from "../src/data";
import { METRICS } from "../src/copy";

const root = new URL("../public/replay/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, root));
const json = (path: string) => JSON.parse(read(path).toString("utf-8")) as unknown;
const results = new URL("../../results/takes/", import.meta.url);
const record = (take: string, file: string) =>
  JSON.parse(readFileSync(new URL(`${take}/${file}`, results)).toString("utf-8")) as Record<string, any>;

const index = checkIndex(json("index.json"));

describe("replay assets", () => {
  it("lists the three graded takes", () => {
    expect(index.map((entry) => entry.take)).toEqual(["take_0525", "take_0526", "take_0527"]);
  });

  it("ships the robot model as a binary glTF", () => {
    const glb = read("g1.glb");
    expect(glb.subarray(0, 4).toString("latin1")).toBe("glTF");
    expect(glb.length).toBeGreaterThan(100_000);
  });

  for (const entry of index) {
    const take = entry.take;
    describe(take, () => {
      const replay = checkReplay(json(`${take}/replay.json`), take);
      const grades = checkGrades(json(`${take}/grades.json`), take);
      const bytes = read(`${take}/frames.bin`);
      const frames = checkFrames(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength), replay);

      it("has a frames.bin that matches its manifest hash", () => {
        expect(createHash("sha256").update(bytes).digest("hex")).toBe(replay.frames_sha256);
      });

      it("names every geom node the GLB carries", () => {
        const glb = read("g1.glb").toString("latin1");
        for (const geom of replay.geoms) expect(glb).toContain(`"name":"${geom.node}"`);
      });

      it("keeps unit quaternions", () => {
        const count = replay.geoms.length;
        for (let f = 0; f < replay.frames; f++) {
          for (let k = 0; k < count; k++) {
            const o = (f * count + k) * FLOATS_PER_GEOM;
            const norm = Math.hypot(frames[o + 3]!, frames[o + 4]!, frames[o + 5]!, frames[o + 6]!);
            expect(Math.abs(norm - 1)).toBeLessThan(1e-3);
          }
        }
      });

      it("drops the pelvis when metrics.json says the root dropped", () => {
        // The pelvis mesh sits a few centimetres below the pelvis body origin that metrics.json
        // measures, so each second's lowest mesh point lands just under the measured root low.
        const metrics = record(take, "metrics.json");
        const count = replay.geoms.length;
        const pelvis = replay.geoms.findIndex((geom) => geom.body === "pelvis");
        expect(pelvis).toBeGreaterThanOrEqual(0);
        for (const second of metrics.per_second as { start_s: number; end_s: number; root_height_min_m: number }[]) {
          const inWindow = Array.from({ length: replay.frames }, (_, f) => f).filter(
            (f) => f / replay.fps >= second.start_s && f / replay.fps <= second.end_s,
          );
          const low = Math.min(...inWindow.map((f) => frames[(f * count + pelvis) * FLOATS_PER_GEOM + 2]!));
          const gap = second.root_height_min_m - low;
          expect(gap).toBeGreaterThan(0);
          expect(gap).toBeLessThan(0.15);
        }
      });

      it("copies the per-second grades from metrics.json exactly", () => {
        const metrics = record(take, "metrics.json");
        expect(grades.seconds).toHaveLength(metrics.per_second.length);
        grades.seconds.forEach((row, i) => {
          const source = metrics.per_second[i];
          expect(row.start_s).toBe(source.start_s);
          expect(row.rules.pass).toBe(source.pass);
          expect(row.rules.reason_codes).toEqual(source.reason_codes);
          for (const spec of METRICS) expect(row.rules[spec.field]).toBe(source[spec.field]);
        });
        expect(grades.overall.reason_codes).toEqual(metrics.overall.reason_codes);
      });

      it("copies the fusion decision and every attempt from fusion.json", () => {
        const fusion = record(take, "fusion.json");
        expect(grades.fusion.final).toEqual(fusion.output);
        expect(grades.fusion.decided_by).toBe(fusion.decided_by);
        expect(grades.fusion.attempts.map((a) => a.guard)).toEqual(fusion.attempts.map((a: { guard: string }) => a.guard));
        expect(grades.fusion.request_id).toBe(fusion.request_id);
      });

      it("copies every run time the page prints from the take records, unrounded", () => {
        const stages = record(take, "driver/stage_timings.json");
        const cosmos = record(take, "visual_summary.json");
        const supervl = record(take, "supervl_summary.json");
        expect(grades.runtime).toEqual({
          gem_x_offline_s: stages.gem_x_offline_s,
          replay_process_wall_s: stages.replay_process_wall_s,
          cosmos_model_load_s: cosmos.timing.model_load_s,
          supervl_wall_s: supervl.timing.wall_s,
          supervl_cost_usd: supervl.cost_usd,
        });
        const fusion = record(take, "fusion.json");
        expect(grades.fusion.attempts.map((a) => a.latency_s)).toEqual(
          fusion.attempts.map((a: { latency_s: number }) => a.latency_s),
        );
        expect(grades.fusion.cost_usd).toBe(fusion.cost_usd);
      });

      it("weighs the two vision models the way the page says", () => {
        // Counted evidence: a measured limit or a Cosmos Reason1 no match. Super VL is not read.
        const counted = (row: (typeof grades.seconds)[number]) => !row.rules.pass || row.cosmos?.match === false;
        for (const w of grades.fusion.final.reshow_windows) {
          const row = grades.seconds.find((r) => r.start_s === w.start_s && r.end_s === w.end_s);
          expect(row !== undefined && counted(row)).toBe(true);
        }
        if (grades.fusion.decided_by === "deterministic_fallback") {
          expect(grades.fusion.final.reshow_windows.map((w) => w.start_s)).toEqual(
            grades.seconds.filter(counted).map((r) => r.start_s),
          );
        }
      });

      it("lines the replay up with the recorded take", () => {
        const timing = record(take, "replay_timing.json");
        expect(replay.frames).toBe(timing.source_frames);
        expect(replay.fps).toBe(timing.source_fps);
      });

      it("carries the frozen cutoffs for every limit the page prints", () => {
        for (const spec of METRICS) {
          if (spec.cutoff !== null) expect(typeof grades.cutoffs[spec.cutoff]).toBe("number");
        }
      });
    });
  }
});
