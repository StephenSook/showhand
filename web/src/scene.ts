// The simulated Unitree G1, posed from frames.bin. Each GLB node holds one MuJoCo geom with its
// vertices in the geom frame, so a frame is just a world position and orientation per node.
// MuJoCo is z up and three.js is y up: every node lives under one group turned -90 degrees
// about x, and the MuJoCo numbers go in unchanged.

import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { FLOATS_PER_GEOM, type Take } from "./data";
import type { FramePick } from "./time";

export interface SceneColors {
  stage: string;
  grid: string;
  pass: string;
  fail: string;
}

const UP_FROM_MUJOCO = new THREE.Euler(-Math.PI / 2, 0, 0);
const BASE_FOV = 32;

export class RobotScene {
  private readonly renderer: THREE.WebGLRenderer;
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(BASE_FOV, 1, 0.05, 50);
  private readonly controls: OrbitControls;
  private readonly root = new THREE.Group();
  private readonly ring: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  private readonly grid: THREE.GridHelper;
  private readonly hemi: THREE.HemisphereLight;
  private readonly sun: THREE.DirectionalLight;
  private readonly parts = new Map<string, THREE.Object3D>();
  private nodes: THREE.Object3D[] = [];
  private pelvis = 0;
  private colors: SceneColors;
  private readonly a = new THREE.Vector3();
  private readonly b = new THREE.Vector3();
  private readonly qa = new THREE.Quaternion();
  private readonly qb = new THREE.Quaternion();
  private readonly world = new THREE.Vector3();

  private constructor(
    private readonly canvas: HTMLCanvasElement,
    model: THREE.Object3D,
    colors: SceneColors,
  ) {
    this.colors = colors;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;

    this.hemi = new THREE.HemisphereLight(0xffffff, colors.stage, 1.6);
    this.sun = new THREE.DirectionalLight(0xffffff, 2.2);
    this.sun.position.set(2.5, 5, 3);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(1024, 1024);
    Object.assign(this.sun.shadow.camera, { left: -2.5, right: 2.5, top: 2.5, bottom: -2.5, near: 0.5, far: 12 });
    this.scene.add(this.hemi, this.sun, this.sun.target);

    const floor = new THREE.Mesh(new THREE.CircleGeometry(6, 64), new THREE.ShadowMaterial({ opacity: 0.16 }));
    floor.rotation.x = -Math.PI / 2;
    floor.receiveShadow = true;
    this.scene.add(floor);
    this.grid = new THREE.GridHelper(8, 32, colors.grid, colors.grid);
    (this.grid.material as THREE.Material).transparent = true;
    (this.grid.material as THREE.Material).opacity = 0.55;
    this.scene.add(this.grid);

    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(0.3, 0.335, 64),
      new THREE.MeshBasicMaterial({ color: colors.pass, side: THREE.DoubleSide }),
    );
    this.ring.rotation.x = -Math.PI / 2;
    this.ring.position.y = 0.002;
    this.scene.add(this.ring);

    this.root.rotation.copy(UP_FROM_MUJOCO);
    this.scene.add(this.root);
    model.traverse((object) => {
      if (/^g\d+$/.test(object.name)) this.parts.set(object.name, object);
      const mesh = object as THREE.Mesh;
      if (!mesh.isMesh) return;
      const geometry = mesh.geometry as THREE.BufferGeometry;
      if (!geometry.getAttribute("normal")) geometry.computeVertexNormals();
      const colored = Boolean(geometry.getAttribute("color"));
      mesh.material = new THREE.MeshStandardMaterial({
        color: colored ? 0xffffff : 0xc9d1ce,
        vertexColors: colored,
        roughness: 0.5,
        metalness: 0.12,
      });
      mesh.castShadow = true;
    });
    for (const part of this.parts.values()) {
      part.matrixAutoUpdate = true;
      this.root.add(part);
    }

    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.enablePan = false;
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 6;
    this.controls.maxPolarAngle = Math.PI / 2 - 0.04;
    this.setColors(colors);
  }

  static async create(canvas: HTMLCanvasElement, glbUrl: string, colors: SceneColors): Promise<RobotScene> {
    const gltf = await new GLTFLoader().loadAsync(glbUrl);
    return new RobotScene(canvas, gltf.scene, colors);
  }

  setColors(colors: SceneColors): void {
    this.colors = colors;
    this.scene.background = new THREE.Color(colors.stage);
    this.hemi.groundColor.set(colors.stage);
    const gridMaterial = this.grid.material as THREE.LineBasicMaterial;
    gridMaterial.color.set(colors.grid);
    gridMaterial.vertexColors = false;
  }

  bind(take: Take): void {
    const missing = take.replay.geoms.filter((geom) => !this.parts.has(geom.node)).map((g) => g.node);
    if (missing.length) throw new Error(`g1.glb has no node for ${missing.join(", ")}`);
    this.nodes = take.replay.geoms.map((geom) => this.parts.get(geom.node)!);
    const pelvis = take.replay.geoms.findIndex((geom) => geom.body === "pelvis");
    if (pelvis < 0) throw new Error(`${take.id}/replay.json has no pelvis geom`);
    this.pelvis = pelvis;
    this.pose(take, { i0: 0, i1: 0, alpha: 0 });
    this.frameCamera(take);
  }

  pose(take: Take, pick: FramePick): void {
    const data = take.frames;
    const count = this.nodes.length;
    for (let k = 0; k < count; k++) {
      const o0 = (pick.i0 * count + k) * FLOATS_PER_GEOM;
      const o1 = (pick.i1 * count + k) * FLOATS_PER_GEOM;
      this.a.set(data[o0]!, data[o0 + 1]!, data[o0 + 2]!);
      this.b.set(data[o1]!, data[o1 + 1]!, data[o1 + 2]!);
      // frames.bin stores w, x, y, z; three.js takes x, y, z, w.
      this.qa.set(data[o0 + 4]!, data[o0 + 5]!, data[o0 + 6]!, data[o0 + 3]!);
      this.qb.set(data[o1 + 4]!, data[o1 + 5]!, data[o1 + 6]!, data[o1 + 3]!);
      const node = this.nodes[k]!;
      node.position.lerpVectors(this.a, this.b, pick.alpha);
      node.quaternion.slerpQuaternions(this.qa, this.qb, pick.alpha);
    }
    const nearest = pick.alpha < 0.5 ? pick.i0 : pick.i1;
    this.ring.material.color.set(take.outOfBalance[nearest] ? this.colors.fail : this.colors.pass);
    this.pelvisWorld(this.world);
    this.ring.position.x = this.world.x;
    this.ring.position.z = this.world.z;
  }

  private pelvisWorld(out: THREE.Vector3): THREE.Vector3 {
    this.root.updateMatrixWorld();
    return this.nodes[this.pelvis]!.getWorldPosition(out);
  }

  frameCamera(take: Take): void {
    const o = this.pelvis * FLOATS_PER_GEOM;
    const d = take.frames;
    const [w, x, y, z] = [d[o + 3]!, d[o + 4]!, d[o + 5]!, d[o + 6]!];
    // The pelvis's local x axis is the way the robot faces, in MuJoCo world coordinates.
    const forward = new THREE.Vector3(1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 0);
    if (forward.lengthSq() < 1e-6) forward.set(1, 0, 0);
    forward.normalize();
    const facing = new THREE.Vector3(forward.x, 0, -forward.y).applyAxisAngle(new THREE.Vector3(0, 1, 0), 0.38);
    const pelvis = this.pelvisWorld(new THREE.Vector3());
    const target = new THREE.Vector3(pelvis.x, pelvis.y - 0.08, pelvis.z);
    this.controls.target.copy(target);
    this.camera.position.copy(target).addScaledVector(facing, 3.1).add(new THREE.Vector3(0, 0.32, 0));
    this.sun.target.position.copy(target);
    this.controls.update();
  }

  // Keep the robot centred as it steps, without fighting a viewer who has orbited the camera.
  follow(): void {
    const pelvis = this.pelvisWorld(this.world);
    const dx = (pelvis.x - this.controls.target.x) * 0.12;
    const dz = (pelvis.z - this.controls.target.z) * 0.12;
    this.controls.target.x += dx;
    this.controls.target.z += dz;
    this.camera.position.x += dx;
    this.camera.position.z += dz;
    this.sun.position.x += dx;
    this.sun.position.z += dz;
    this.sun.target.position.copy(this.controls.target);
  }

  resize(): void {
    const width = this.canvas.clientWidth;
    const height = this.canvas.clientHeight;
    if (width === 0 || height === 0) return;
    const size = this.renderer.getSize(new THREE.Vector2());
    if (size.x === width && size.y === height) return;
    this.renderer.setSize(width, height, false);
    this.camera.aspect = width / height;
    // A tall, narrow pane (a phone) would crop outstretched arms; open the vertical field of view
    // part of the way toward keeping the horizontal one, without the distortion of going all the way.
    const base = Math.tan(THREE.MathUtils.degToRad(BASE_FOV / 2));
    const widen = this.camera.aspect < 1 ? Math.pow(this.camera.aspect, -0.6) : 1;
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(base * widen));
    this.camera.updateProjectionMatrix();
  }

  render(): void {
    this.resize();
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}
