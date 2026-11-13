"use client";

import { OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { terrainUrl, type TerrainMeta } from "@/lib/api";
import { colorAt } from "@/lib/style";

type Props = {
  studyId: string;
  meta: TerrainMeta;
  date: string | null;
  drapeUrl: string | null;
  k: number;
  kd: number;
  onPick: (lon: number, lat: number) => void;
  reduced: boolean;
};

const SIZE = 10; // scene units across the longer side

async function f32(url: string) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`Could not load ${url.split("/").pop()}`);
  return new Float32Array(await r.arrayBuffer());
}

function Surface({ studyId, meta, date, drapeUrl, k, kd, onPick, reduced }: Props) {
  const [H, W] = meta.shape;
  const scale = SIZE / (Math.max(H, W) * meta.cell_m); // metres -> scene units
  const [dem, setDem] = useState<Float32Array | null>(null);
  const [loaded, setLoaded] = useState<Record<string, Float32Array | null>>({});
  const disp = date ? loaded[date] ?? null : null;
  const mesh = useRef<THREE.Mesh>(null);
  const target = useRef<Float32Array | null>(null);
  const morphing = useRef(false);

  useEffect(() => {
    f32(terrainUrl(studyId, "dem.f32")).then(setDem).catch(() => setDem(new Float32Array(H * W)));
  }, [studyId, H, W]);

  useEffect(() => {
    if (!date || date in loaded) return;
    f32(terrainUrl(studyId, `disp_${date}.f32`))
      .then((a) => setLoaded((l) => ({ ...l, [date]: a })))
      .catch(() => setLoaded((l) => ({ ...l, [date]: null })));
  }, [studyId, date, loaded]);

  const geometry = useMemo(() => {
    const g = new THREE.PlaneGeometry(W * meta.cell_m * scale, H * meta.cell_m * scale, W - 1, H - 1);
    g.rotateX(-Math.PI / 2);
    g.setAttribute("color", new THREE.BufferAttribute(new Float32Array(H * W * 3).fill(0.5), 3));
    return g;
  }, [H, W, meta.cell_m, scale]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  const dispRange = useMemo(() => {
    if (!disp) return 1;
    let m = 0;
    for (let i = 0; i < disp.length; i += 7) if (Number.isFinite(disp[i])) m = Math.max(m, Math.abs(disp[i]));
    return Math.max(1, m);
  }, [disp]);

  // Target heights for the current date; the mesh eases toward them (the time morph).
  useEffect(() => {
    if (!dem) return;
    const t = new Float32Array(H * W);
    const col = geometry.getAttribute("color") as THREE.BufferAttribute;
    for (let i = 0; i < H * W; i++) {
      const z = Number.isFinite(dem[i]) ? dem[i] : 0;
      const d = disp && Number.isFinite(disp[i]) ? disp[i] / 100 : 0; // cm -> m
      t[i] = (z * k + d * kd) * scale;
      if (!drapeUrl) {
        const c = disp && Number.isFinite(disp[i]) ? colorAt("rdbu", 0.5 + disp[i] / (2 * dispRange)) : ([0.42, 0.45, 0.5] as const);
        col.setXYZ(i, c[0], c[1], c[2]);
      }
    }
    col.needsUpdate = true;
    target.current = t;
    morphing.current = true;
    if (reduced) {
      const pos = geometry.getAttribute("position") as THREE.BufferAttribute;
      for (let i = 0; i < t.length; i++) pos.setY(i, t[i]);
      pos.needsUpdate = true;
      geometry.computeVertexNormals();
      morphing.current = false;
    }
  }, [dem, disp, k, kd, scale, H, W, geometry, drapeUrl, dispRange, reduced]);

  useFrame((_, dt) => {
    if (!morphing.current || !target.current) return;
    const pos = geometry.getAttribute("position") as THREE.BufferAttribute;
    const a = Math.min(1, dt * 6);
    let moving = false;
    const t = target.current;
    for (let i = 0; i < t.length; i++) {
      const y = pos.getY(i);
      const ny = y + (t[i] - y) * a;
      if (Math.abs(t[i] - ny) > 1e-5) moving = true;
      pos.setY(i, ny);
    }
    pos.needsUpdate = true;
    geometry.computeVertexNormals();
    morphing.current = moving;
  });

  const [drapeTex, setDrapeTex] = useState<{ url: string; tex: THREE.Texture } | null>(null);
  const texture = drapeUrl && drapeTex?.url === drapeUrl ? drapeTex.tex : null;
  useEffect(() => {
    if (!drapeUrl) return;
    let alive = true;
    const loader = new THREE.TextureLoader();
    loader.setCrossOrigin("anonymous");
    loader.load(drapeUrl, (tex) => {
      if (!alive) return tex.dispose();
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 4;
      setDrapeTex((old) => {
        old?.tex.dispose();
        return { url: drapeUrl, tex };
      });
    });
    return () => {
      alive = false;
    };
  }, [drapeUrl]);

  const click = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation();
    if (!e.uv) return;
    const [w, s, east, n] = meta.bbox;
    onPick(w + e.uv.x * (east - w), s + e.uv.y * (n - s));
  };

  return (
    <mesh ref={mesh} geometry={geometry} onClick={click}>
      {texture ? <meshStandardMaterial key="tex" map={texture} roughness={0.95} metalness={0} /> : <meshStandardMaterial key="col" vertexColors roughness={0.9} metalness={0} />}
    </mesh>
  );
}

export default function Terrain3D(props: Props) {
  return (
    <Canvas camera={{ position: [0, 6, 9], fov: 40, near: 0.05, far: 200 }} dpr={[1, 2]} aria-label="3D view of the terrain and ground motion">
      <color attach="background" args={["#05070a"]} />
      <hemisphereLight args={["#dbe7ff", "#1b1f27", 0.9]} />
      <directionalLight position={[-6, 8, 4]} intensity={1.6} />
      <Surface {...props} />
      <OrbitControls makeDefault enableDamping maxPolarAngle={Math.PI / 2.1} minDistance={2} maxDistance={30} />
    </Canvas>
  );
}
