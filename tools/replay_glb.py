"""Build the browser replay's robot model and frame files from an export_replay.py output.

Reads <export>/meshes.npz and replay.json for one take, keeps one geom per (body, mesh) pair (the
model carries a visual and a collision geom with the same pose for each link), decimates each mesh
with quadric simplification, and writes:

  <web>/g1.glb                one node per kept geom, named g<order>, vertices in the geom frame
  <web>/<take>/frames.bin     float32 [frame][kept geom][x, y, z, qw, qx, qy, qz]
  <web>/<take>/replay.json    kept geoms, fps, frame times, and source hashes

Run with the sci venv (trimesh + fast_simplification):
  python tools/replay_glb.py --export artifacts/replay --web web/public/replay
    --takes take_0525 take_0526 take_0527
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh


def kept_geoms(geoms: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    kept = []
    for geom in geoms:
        key = (geom["body"], geom["mesh"])
        if key in seen:
            continue
        seen.add(key)
        kept.append(geom)
    return kept


def build_glb(meshes: np.lib.npyio.NpzFile, geoms: list[dict], ratio: float, out: Path) -> dict:
    scene = trimesh.Scene()
    faces_in = faces_out = 0
    for geom in geoms:
        order = geom["order"]
        mesh = trimesh.Trimesh(
            vertices=meshes[f"v{order}"], faces=meshes[f"f{order}"], process=True
        )
        faces_in += len(mesh.faces)
        target = max(64, int(len(mesh.faces) * ratio))
        if len(mesh.faces) > target:
            mesh = mesh.simplify_quadric_decimation(face_count=target)
        faces_out += len(mesh.faces)
        rgba = [round(channel * 255) for channel in geom["rgba"]]
        mesh.visual = trimesh.visual.ColorVisuals(
            mesh, face_colors=np.tile(rgba, (len(mesh.faces), 1))
        )
        scene.add_geometry(mesh, node_name=f"g{order}", geom_name=f"g{order}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(scene.export(file_type="glb"))
    return {"faces_in": faces_in, "faces_out": faces_out, "bytes": out.stat().st_size}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--web", type=Path, required=True)
    parser.add_argument("--takes", nargs="+", required=True)
    parser.add_argument("--ratio", type=float, default=0.1)
    args = parser.parse_args()

    first = json.loads((args.export / args.takes[0] / "replay.json").read_text(encoding="utf-8"))
    kept = kept_geoms(first["geoms"])
    with np.load(args.export / args.takes[0] / "meshes.npz") as meshes:
        glb = build_glb(meshes, kept, args.ratio, args.web / "g1.glb")

    summary = {"glb": glb, "kept_geoms": len(kept), "takes": {}}
    for take in args.takes:
        replay = json.loads((args.export / take / "replay.json").read_text(encoding="utf-8"))
        if [geom["mesh"] for geom in replay["geoms"]] != [geom["mesh"] for geom in first["geoms"]]:
            raise SystemExit(f"{take} was exported from a different model than {args.takes[0]}")
        frames = np.frombuffer((args.export / take / "frames.bin").read_bytes(), dtype=np.float32)
        frames = frames.reshape(replay["frames"], len(replay["geoms"]), 7)[
            :, [geom["order"] for geom in kept], :
        ]
        out_dir = args.web / take
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "frames.bin").write_bytes(np.ascontiguousarray(frames).tobytes())
        manifest = {
            "schema_version": 1,
            "take": take,
            "fps": replay["fps"],
            "frames": replay["frames"],
            "geoms": [{"node": f"g{geom['order']}", "body": geom["body"]} for geom in kept],
            "frame_layout": replay["frame_layout"],
            "frame_times": replay["frame_times"],
            "source_frames_sha256": replay["frames_sha256"],
            "telemetry_sha256": replay["telemetry_sha256"],
            "frames_sha256": hashlib.sha256((out_dir / "frames.bin").read_bytes()).hexdigest(),
        }
        (out_dir / "replay.json").write_text(
            json.dumps(manifest, separators=(",", ":")) + "\n", encoding="utf-8"
        )
        summary["takes"][take] = {
            "frames": replay["frames"],
            "bytes": (out_dir / "frames.bin").stat().st_size,
        }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
