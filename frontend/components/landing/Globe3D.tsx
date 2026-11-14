"use client";

import { Stars } from "@react-three/drei";
import { Canvas, useFrame, useLoader, useThree } from "@react-three/fiber";
import { Suspense, useMemo, useRef } from "react";
import * as THREE from "three";

/**
 * The home page's Earth: NASA Blue Marble by day and Black Marble city lights by night, split by a soft
 * terminator, under a teal atmosphere, with NISAR on its orbit pointing its radar at the ground. It flies between
 * three framings as the story scrolls: a huge horizon (hero), the whole planet (intro), and a small locator in
 * the corner turned to the place a chapter is about.
 */

export type GlobeMode = "hero" | "intro" | "focus" | "corner";
export type GlobeFocus = { mode: GlobeMode; lat?: number; lon?: number; marker?: string | null };
export type GlobeMarker = { id: string; lat: number; lon: number; color: string };

const D2R = Math.PI / 180;

/** Lon/lat to a point on the unit sphere, matching three.js SphereGeometry UVs (lon 0 at +x, lon -90 at +z). */
export function ll(lat: number, lon: number, r = 1) {
  const la = lat * D2R;
  const lo = lon * D2R;
  return new THREE.Vector3(r * Math.cos(la) * Math.cos(lo), r * Math.sin(la), -r * Math.cos(la) * Math.sin(lo));
}

const EARTH_VERT = /* glsl */ `
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
void main() {
  vUv = uv;
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const EARTH_FRAG = /* glsl */ `
uniform sampler2D dayTex; uniform sampler2D nightTex; uniform vec3 sunDir; uniform vec3 tint;
varying vec2 vUv; varying vec3 vN; varying vec3 vW;
void main() {
  vec3 n = normalize(vN);
  float d = dot(n, normalize(sunDir));
  float dayMix = smoothstep(-0.16, 0.24, d);
  vec3 day = texture2D(dayTex, vUv).rgb;
  vec3 night = texture2D(nightTex, vUv).rgb;
  vec3 lights = pow(night, vec3(1.8)) * vec3(1.9, 1.45, 0.95) * 2.4;     // warm city lights
  vec3 nightSide = lights + night * vec3(0.22, 0.32, 0.45);
  vec3 daySide = day * (0.28 + 0.9 * max(d, 0.0));
  vec3 col = mix(nightSide, daySide, dayMix);
  // a thin teal glow along the terminator, and a rim towards the limb
  col += tint * exp(-pow(d * 9.0, 2.0)) * 0.12;
  vec3 v = normalize(cameraPosition - vW);
  float rim = pow(1.0 - max(dot(n, v), 0.0), 3.0);
  col += mix(vec3(0.20, 0.78, 0.85), tint, 0.7) * rim * 0.55;
  gl_FragColor = vec4(col, 1.0);
}`;

const ATMO_VERT = /* glsl */ `
varying vec3 vN; varying vec3 vW;
void main() {
  vN = normalize(mat3(modelMatrix) * normal);
  vec4 w = modelMatrix * vec4(position, 1.0);
  vW = w.xyz;
  gl_Position = projectionMatrix * viewMatrix * w;
}`;

const ATMO_FRAG = /* glsl */ `
uniform vec3 glow; varying vec3 vN; varying vec3 vW;
void main() {
  vec3 v = normalize(cameraPosition - vW);
  float i = pow(clamp(0.78 + dot(normalize(vN), v), 0.0, 1.0), 4.0);
  gl_FragColor = vec4(glow, 1.0) * i * 1.4;
}`;

function wrap(a: number) {
  return Math.atan2(Math.sin(a), Math.cos(a));
}

type Props = { focus: GlobeFocus; markers: GlobeMarker[]; reduced: boolean; tint?: string };

function Earth({ focus, markers, reduced, tint = "#2dd4bf" }: Props) {
  const [day, night] = useLoader(THREE.TextureLoader, ["/textures/earth-day.jpg", "/textures/earth-night.jpg"]);
  const outer = useRef<THREE.Group>(null); // tilt (latitude) and placement
  const inner = useRef<THREE.Group>(null); // spin (longitude)
  const orbit = useRef<THREE.Group>(null);
  const rings = useRef<THREE.Mesh[]>([]);
  const { viewport } = useThree();
  const mat = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { dayTex: { value: day }, nightTex: { value: night }, sunDir: { value: new THREE.Vector3(-1, 0.25, 0.35) }, tint: { value: new THREE.Color("#2dd4bf") } },
    vertexShader: EARTH_VERT,
    fragmentShader: EARTH_FRAG,
  }), [day, night]);
  const atmo = useMemo(() => new THREE.ShaderMaterial({
    uniforms: { glow: { value: new THREE.Color("#2dd4bf") } },
    vertexShader: ATMO_VERT,
    fragmentShader: ATMO_FRAG,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
  }), []);
  const orbitLine = useMemo(() => {
    const pts = Array.from({ length: 129 }, (_, i) => new THREE.Vector3(Math.cos((i / 128) * Math.PI * 2) * 1.34, 0, Math.sin((i / 128) * Math.PI * 2) * 1.34));
    return new THREE.BufferGeometry().setFromPoints(pts);
  }, []);
  const sunTarget = useMemo(() => new THREE.Vector3(), []);
  const tintTarget = useMemo(() => new THREE.Color(tint), [tint]);
  const orbitMat = useRef<THREE.LineBasicMaterial>(null);

  useFrame((state, dt) => {
    const o = outer.current;
    const n = inner.current;
    if (!o || !n) return;
    const k = Math.min(1, dt * 2.2); // easing rate
    const wide = viewport.width > viewport.height;
    // framing for each mode, in world units at the globe's depth
    let px = 0, py = 0, sc = 1, tiltX = 0.38, sun: [number, number, number] = [-1, 0.25, 0.35];
    if (focus.mode === "hero") {
      py = -viewport.height * 0.52;
      sc = wide ? Math.min(1.55, viewport.width * 0.42) : viewport.width * 0.62;
    } else if (focus.mode === "intro") {
      sc = Math.min(0.95, viewport.height * 0.36);
      px = wide ? viewport.width * 0.2 : 0;
      py = wide ? 0 : viewport.height * 0.16;
      sun = [-0.55, 0.35, 0.9];
    } else if (focus.mode === "focus") {
      sc = Math.min(0.9, viewport.height * 0.34);
      px = wide ? viewport.width * 0.2 : 0;
      py = wide ? 0 : viewport.height * 0.18;
      tiltX = (focus.lat ?? 0) * D2R;
      sun = [-0.35, 0.4, 1];
    } else {
      // a locator, tucked under the navigation bar on the right
      sc = wide ? 0.2 : 0.16;
      px = viewport.width / 2 - sc * 1.25 - (wide ? 0.12 : 0.06);
      py = viewport.height / 2 - sc * 1.25 - (wide ? 0.3 : 0.26);
      tiltX = (focus.lat ?? 0) * D2R;
      sun = [-0.35, 0.4, 1];
    }
    o.position.x += (px - o.position.x) * k;
    o.position.y += (py - o.position.y) * k;
    const s = o.scale.x + (sc - o.scale.x) * k;
    o.scale.setScalar(s);
    o.rotation.x += (tiltX - o.rotation.x) * k;
    // spin: free in hero and intro, turned to the place in corner mode (shortest way round)
    if ((focus.mode === "corner" || focus.mode === "focus") && focus.lon !== undefined) {
      const target = -Math.PI / 2 - focus.lon * D2R;
      n.rotation.y += wrap(target - n.rotation.y) * k;
    } else if (!reduced) {
      n.rotation.y += 0.05 * dt; // a slow turn, about two minutes per revolution
    }
    sunTarget.set(...sun).normalize();
    mat.uniforms.sunDir.value.lerp(sunTarget, k);
    // the chapter's colour, eased in over about a second
    const kc = Math.min(1, dt * 1.6);
    mat.uniforms.tint.value.lerp(tintTarget, kc);
    atmo.uniforms.glow.value.lerp(tintTarget, kc);
    orbitMat.current?.color.lerp(tintTarget, kc);
    if (orbit.current && !reduced) orbit.current.rotation.y += dt * 0.35;
    const t = state.clock.elapsedTime;
    rings.current.forEach((r, i) => {
      if (!r) return;
      const ph = (t * 0.6 + i * 0.37) % 1;
      const active = markers[i]?.id === focus.marker;
      r.scale.setScalar((active ? 1.6 : 1) * (1 + ph * 2.2));
      (r.material as THREE.MeshBasicMaterial).opacity = (1 - ph) * (active ? 0.95 : 0.55);
    });
  });

  return (
    <group ref={outer}>
      <group ref={inner}>
        <mesh material={mat}><sphereGeometry args={[1, 128, 128]} /></mesh>
        {markers.map((m, i) => {
          const p = ll(m.lat, m.lon, 1.004);
          const q = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 0, 1), p.clone().normalize());
          return (
            <group key={m.id} position={p} quaternion={q}>
              <mesh><circleGeometry args={[0.012, 24]} /><meshBasicMaterial color={m.color} toneMapped={false} /></mesh>
              <mesh ref={(el) => { if (el) rings.current[i] = el; }}>
                <ringGeometry args={[0.016, 0.021, 40]} />
                <meshBasicMaterial color={m.color} transparent opacity={0.6} toneMapped={false} depthWrite={false} />
              </mesh>
            </group>
          );
        })}
      </group>
      <mesh material={atmo} scale={1.16}><sphereGeometry args={[1, 64, 64]} /></mesh>
      {/* NISAR: a tilted near-polar orbit; the satellite carries a translucent radar beam aimed at the ground */}
      <group rotation={[1.05, 0.2, 0.35]}>
        <lineLoop geometry={orbitLine}><lineBasicMaterial ref={orbitMat} color="#5eead4" transparent opacity={0.35} /></lineLoop>
        <group ref={orbit}>
          <group position={[1.34, 0, 0]}>
            <mesh><boxGeometry args={[0.035, 0.022, 0.022]} /><meshBasicMaterial color="#e4f2f4" /></mesh>
            <mesh position={[0, 0, 0.055]}><boxGeometry args={[0.012, 0.004, 0.07]} /><meshBasicMaterial color="#38bdf8" /></mesh>
            <mesh position={[0, 0, -0.055]}><boxGeometry args={[0.012, 0.004, 0.07]} /><meshBasicMaterial color="#38bdf8" /></mesh>
            {/* cone tip (+y) turned to +x: narrow at the satellite, wide where it meets the ground */}
            <mesh position={[-0.17, 0, 0]} rotation={[0, 0, -Math.PI / 2]}>
              <coneGeometry args={[0.07, 0.32, 32, 1, true]} />
              <meshBasicMaterial color="#5eead4" transparent opacity={0.22} side={THREE.DoubleSide} depthWrite={false} blending={THREE.AdditiveBlending} />
            </mesh>
          </group>
        </group>
      </group>
    </group>
  );
}

export default function Globe3D({ focus, markers, reduced, tint }: Props) {
  return (
    <Canvas camera={{ position: [0, 0, 3.4], fov: 40 }} dpr={[1, 2]} gl={{ antialias: true, alpha: true }} style={{ pointerEvents: "none" }}>
      <Stars radius={60} depth={40} count={2600} factor={2.6} saturation={0} fade speed={reduced ? 0 : 0.4} />
      <Suspense fallback={null}>
        <Earth focus={focus} markers={markers} reduced={reduced} tint={tint} />
      </Suspense>
    </Canvas>
  );
}
