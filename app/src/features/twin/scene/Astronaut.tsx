// The astronaut, built only from primitives (spheres, capsules, boxes, torus). No models, textures
// or HDR files are loaded: everything is generated in code, so the scene works offline.
// A generic, stylised suit of our own design (not a real person, mascot or brand).
//
// Animation runs in useFrame with refs (no React state per frame). With reduced motion there is
// no float and no heart pulse (the bpm is shown as text in the panel instead).
import { useFrame, type ThreeEvent } from '@react-three/fiber';
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import * as THREE from 'three';
import type { TwinTheme } from '../env';
import type { RegionId, TwinRegion, TwinSensor } from '../types';
import { beatPeriod, numberSensors } from '../twinView';
import { FOCUS } from './layout';

const ANCHOR_POS: Record<NonNullable<TwinSensor['anchor']>, [number, number, number]> = {
  chest: [0, 0.03, 0.255], // chest strap, front of the torso
  upperArm: [-0.4, 0.3, 0.06], // skin temperature patch (marker just under the patch)
  leftWrist: [0.4, -0.03, 0.08], // wrist oximeter, astronaut's left wrist
};

type HoverFn = (id: RegionId | null, e?: ThreeEvent<PointerEvent>) => void;

export interface AstronautProps {
  regions: Partial<Record<RegionId, TwinRegion>>;
  theme: TwinTheme;
  selected: RegionId | null;
  hovered: RegionId | null;
  reducedMotion: boolean;
  onHover: HoverFn;
  onSelect: (id: RegionId) => void;
}

// ---- small building blocks ----------------------------------------------------------------
/** Suit parts: block pointer events so the regions behind them are not picked through the body. */
function Suit({ children, ...rest }: { children: ReactNode } & JSX.IntrinsicElements['mesh']) {
  return (
    <mesh
      {...rest}
      onPointerOver={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      {children}
    </mesh>
  );
}

/** A dashed ring facing the camera's default direction (+z): the "No data" outline. */
function DashedRing({ radius, color, position }: { radius: number; color: string; position: [number, number, number] }) {
  const line = useMemo(() => {
    const pts = Array.from({ length: 49 }, (_, i) => {
      const a = (i / 48) * Math.PI * 2;
      return new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0);
    });
    const geo = new THREE.BufferGeometry().setFromPoints(pts);
    const mat = new THREE.LineDashedMaterial({ color, dashSize: radius * 0.35, gapSize: radius * 0.25, transparent: true, opacity: 0.8 });
    const l = new THREE.Line(geo, mat);
    l.computeLineDistances();
    return l;
  }, [radius, color]);
  useEffect(() => () => {
    line.geometry.dispose();
    (line.material as THREE.Material).dispose();
  }, [line]);
  // Not pickable: three.js picks lines within a wide threshold, which would steal clicks from regions.
  return <primitive object={line} position={position} raycast={() => null} />;
}

function regionMaterialProps(region: TwinRegion | undefined, theme: TwinTheme, active: boolean) {
  const status = region?.status ?? 'nodata';
  const color = theme.status[status];
  const nodata = status === 'nodata';
  return {
    color,
    emissive: color,
    emissiveIntensity: nodata ? 0.05 : active ? 1.4 : 0.7,
    roughness: 0.45,
    metalness: 0.05,
    transparent: nodata,
    opacity: nodata ? 0.35 : 1,
  };
}

interface RegionProps {
  id: RegionId;
  region: TwinRegion | undefined;
  theme: TwinTheme;
  active: boolean;
  onHover: HoverFn;
  onSelect: (id: RegionId) => void;
  /** Render the region's meshes with the shared status material. */
  children: (material: THREE.Material) => ReactNode;
  ringRadius?: number;
  ringAt?: [number, number, number];
}

/** Event handlers shared by every clickable region mesh. */
function useRegionEvents(id: RegionId, onHover: HoverFn, onSelect: (id: RegionId) => void) {
  return useMemo(
    () => ({
      onPointerOver: (e: ThreeEvent<PointerEvent>) => {
        e.stopPropagation();
        onHover(id, e);
      },
      onPointerOut: () => onHover(null),
      onClick: (e: ThreeEvent<MouseEvent>) => {
        e.stopPropagation();
        onSelect(id);
      },
    }),
    [id, onHover, onSelect],
  );
}

/** A clickable body region: glows in its status colour; "No data" = faint grey + dashed outline. */
function Region({ id, region, theme, active, onHover, onSelect, children, ringRadius, ringAt }: RegionProps) {
  const events = useRegionEvents(id, onHover, onSelect);
  const material = useMemo(() => new THREE.MeshStandardMaterial(), []);
  useEffect(() => () => material.dispose(), [material]);
  const m = regionMaterialProps(region, theme, active);
  useEffect(() => {
    material.color.set(m.color);
    material.emissive.set(m.emissive);
    material.emissiveIntensity = m.emissiveIntensity;
    material.roughness = m.roughness;
    material.metalness = m.metalness;
    material.transparent = m.transparent;
    material.opacity = m.opacity;
    material.needsUpdate = true;
  }, [material, m.color, m.emissive, m.emissiveIntensity, m.roughness, m.metalness, m.transparent, m.opacity]);
  return (
    <group name={`region-${id}`} {...events}>
      {children(material)}
      {region?.status === 'nodata' && ringRadius && ringAt && (
        <DashedRing radius={ringRadius} color={theme.status.nodata} position={ringAt} />
      )}
    </group>
  );
}

// ---- number sprites for the sensor markers ---------------------------------------------------
function useNumberTexture(n: number, fg: string, bg: string) {
  const tex = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const g = c.getContext('2d');
    if (g) {
      g.fillStyle = bg;
      g.beginPath();
      g.arc(32, 32, 28, 0, Math.PI * 2);
      g.fill();
      g.lineWidth = 4;
      g.strokeStyle = fg;
      g.stroke();
      g.fillStyle = fg;
      g.font = `bold 34px ${getComputedStyle(document.documentElement).getPropertyValue('--font-body') || 'sans-serif'}`;
      g.textAlign = 'center';
      g.textBaseline = 'middle';
      g.fillText(String(n), 32, 34);
    }
    const t = new THREE.CanvasTexture(c);
    t.colorSpace = THREE.SRGBColorSpace;
    return t;
  }, [n, fg, bg]);
  useEffect(() => () => tex.dispose(), [tex]);
  return tex;
}

function SensorMarker({ sensor, n, theme, active, onHover, onSelect }: {
  sensor: TwinSensor; n: number; theme: TwinTheme; active: boolean; onHover: HoverFn; onSelect: (id: RegionId) => void;
}) {
  const pos = ANCHOR_POS[sensor.anchor!];
  const color = sensor.status === 'connected' ? theme.ok : sensor.status === 'low_battery' ? theme.status.review : theme.danger;
  const tex = useNumberTexture(n, color, theme.background);
  const events = useRegionEvents('sensors', onHover, onSelect);
  const out = sensor.anchor === 'upperArm' ? -1 : sensor.anchor === 'leftWrist' ? 1 : 0;
  return (
    <group position={pos} {...events} name={`sensor-${sensor.id}`}>
      <mesh>
        <sphereGeometry args={[0.024, 12, 8]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={active ? 1.5 : 0.9} />
      </mesh>
      <sprite position={[out * 0.09, 0.07, 0.04]} scale={[0.075, 0.075, 0.075]}>
        <spriteMaterial map={tex} depthTest={false} transparent />
      </sprite>
    </group>
  );
}

// ---- stars ---------------------------------------------------------------------------------
function Stars({ color }: { color: string }) {
  const geo = useMemo(() => {
    // Deterministic LCG: the same static star field on every load.
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const n = 350;
    const arr = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      const u = rnd() * 2 - 1;
      const t = rnd() * Math.PI * 2;
      const r = 18 + rnd() * 14;
      const s = Math.sqrt(1 - u * u);
      arr.set([r * s * Math.cos(t), r * u, r * s * Math.sin(t)], i * 3);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(arr, 3));
    return g;
  }, []);
  useEffect(() => () => geo.dispose(), [geo]);
  return (
    <points geometry={geo} raycast={() => null}>
      <pointsMaterial color={color} size={0.09} sizeAttenuation transparent opacity={0.85} />
    </points>
  );
}

// ---- the astronaut ---------------------------------------------------------------------------
export function Astronaut({ regions, theme, selected, hovered, reducedMotion, onHover, onSelect }: AstronautProps) {
  const body = useRef<THREE.Group>(null);
  const heart = useRef<THREE.Group>(null);
  const phase = useRef(0);
  const period = useRef<number | null>(null);
  const heartRegion = regions.heart;

  useEffect(() => {
    period.current = beatPeriod(heartRegion?.pulseBpm);
  }, [heartRegion?.pulseBpm]);

  useEffect(() => {
    if (reducedMotion) {
      body.current?.position.set(0, 0, 0);
      body.current?.rotation.set(0, 0, 0);
      heart.current?.scale.setScalar(1);
    }
  }, [reducedMotion]);

  useFrame(({ clock }, dt) => {
    if (reducedMotion) return;
    const t = clock.getElapsedTime();
    if (body.current) {
      body.current.position.y = Math.sin(t * 0.55) * 0.05; // gentle microgravity bob
      body.current.rotation.z = Math.sin(t * 0.37) * 0.035;
      body.current.rotation.x = Math.sin(t * 0.29) * 0.02;
    }
    if (heart.current) {
      const p = period.current;
      if (p === null) {
        heart.current.scale.setScalar(1);
      } else {
        phase.current = (phase.current + Math.min(dt, 0.1) / p) % 1;
        const x = phase.current;
        // "lub-dub": a strong beat then a smaller one, then rest.
        const beat = x < 0.12 ? Math.sin((x / 0.12) * Math.PI) : x > 0.18 && x < 0.28 ? 0.5 * Math.sin(((x - 0.18) / 0.1) * Math.PI) : 0;
        heart.current.scale.setScalar(1 + 0.22 * beat);
      }
    }
  });

  const radEvents = useRegionEvents('radiation', onHover, onSelect);
  const act = (id: RegionId) => selected === id || hovered === id;
  const common = { theme, onHover, onSelect };
  const sensors = numberSensors(regions.sensors?.sensors ?? []).filter((s) => s.marker !== null);
  const patch = regions.sensors?.sensors?.find((s) => s.anchor === 'upperArm');
  const rad = regions.radiation;
  const radColor = rad && (rad.status === 'review' || rad.status === 'urgent') ? theme.status[rad.status] : theme.neutral;

  const suitMat = <meshStandardMaterial color={theme.suit} roughness={0.75} metalness={0.05} />;
  const shadeMat = <meshStandardMaterial color={theme.suitShade} roughness={0.8} />;

  return (
    <>
      <Stars color={theme.star} />
      <group ref={body}>
        {/* helmet: a clear shell (the brain glows inside) and a dark visor */}
        {/* helmet shell and visor are click-through, so the brain and eyes inside can be picked */}
        <Suit position={[0, 0.78, 0]} raycast={() => null}>
          <sphereGeometry args={[0.28, 24, 16]} />
          <meshStandardMaterial color={theme.suit} transparent opacity={0.22} roughness={0.2} depthWrite={false} />
        </Suit>
        <Suit position={[0, 0.78, 0]} raycast={() => null}>
          <sphereGeometry args={[0.285, 24, 12, Math.PI / 2 - 0.95, 1.9, 1.08, 1.0]} />
          <meshStandardMaterial color={theme.visor} roughness={0.1} metalness={0.6} transparent opacity={0.72} depthWrite={false} side={THREE.DoubleSide} />
        </Suit>
        <Suit position={[0, 0.54, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.17, 0.04, 8, 24]} />
          {shadeMat}
        </Suit>

        {/* torso, chest strap band and backpack */}
        <Suit position={[0, 0.22, 0]}>
          <capsuleGeometry args={[0.24, 0.42, 6, 18]} />
          {suitMat}
        </Suit>
        <Suit position={[0, 0.03, 0]} rotation={[Math.PI / 2, 0, 0]}>
          <torusGeometry args={[0.243, 0.012, 6, 32]} />
          {shadeMat}
        </Suit>
        <Suit position={[0, 0.28, -0.3]}>
          <boxGeometry args={[0.46, 0.56, 0.2]} />
          {shadeMat}
        </Suit>

        {/* arms and gloves */}
        {[1, -1].map((side) => (
          <group key={side}>
            <Suit position={[side * 0.34, 0.2, 0]} rotation={[0, 0, side * 0.18]}>
              <capsuleGeometry args={[0.075, 0.5, 4, 12]} />
              {suitMat}
            </Suit>
            <Suit position={[side * 0.4, -0.13, 0]}>
              <sphereGeometry args={[0.085, 14, 10]} />
              {shadeMat}
            </Suit>
          </group>
        ))}

        {/* legs and boots */}
        {[1, -1].map((side) => (
          <group key={side}>
            <Suit position={[side * 0.13, -0.52, 0]}>
              <capsuleGeometry args={[0.095, 0.55, 4, 12]} />
              {suitMat}
            </Suit>
            <Suit position={[side * 0.13, -0.93, 0.04]}>
              <boxGeometry args={[0.17, 0.12, 0.26]} />
              {shadeMat}
            </Suit>
          </group>
        ))}

        {/* ---- body regions ---- */}
        <Region id="brain" region={regions.brain} active={act('brain')} ringRadius={0.15} ringAt={[0, 0.88, 0.29]} {...common}>
          {(mat) => (
            <mesh position={[0, 0.87, -0.02]} scale={[1, 0.8, 1.1]} material={mat}>
              <sphereGeometry args={[0.12, 20, 14]} />
            </mesh>
          )}
        </Region>

        <Region id="eyes" region={regions.eyes} active={act('eyes')} ringRadius={0.12} ringAt={[0, 0.77, 0.3]} {...common}>
          {(mat) =>
            [1, -1].map((side) => (
              <mesh key={side} position={[side * 0.075, 0.77, 0.275]} scale={[1, 0.7, 0.45]} material={mat}>
                <sphereGeometry args={[0.036, 14, 10]} />
              </mesh>
            ))
          }
        </Region>

        <Region id="lungs" region={regions.lungs} active={act('lungs')} ringRadius={0.2} ringAt={[0, 0.36, 0.26]} {...common}>
          {(mat) =>
            [1, -1].map((side) => (
              <mesh key={side} position={[side * 0.11, 0.37, 0.2]} scale={[0.85, 1.3, 0.5]} material={mat}>
                <sphereGeometry args={[0.08, 16, 12]} />
              </mesh>
            ))
          }
        </Region>

        <group ref={heart} position={[0.03, 0.31, 0.235]}>
          <Region id="heart" region={heartRegion} active={act('heart')} ringRadius={0.08} ringAt={[0, 0, 0.04]} {...common}>
            {(mat) => (
              <mesh material={mat}>
                <sphereGeometry args={[0.055, 16, 12]} />
              </mesh>
            )}
          </Region>
        </group>

        <Region id="bones" region={regions.bones} active={act('bones')} ringRadius={0.12} ringAt={[0, -0.52, 0.12]} {...common}>
          {(mat) => (
            <>
              {/* spine through the torso (seen through the open helmet ring / from behind) */}
              <mesh position={[0, 0.25, -0.05]} material={mat}>
                <capsuleGeometry args={[0.028, 0.6, 4, 8]} />
              </mesh>
              {/* weight-bearing leg bones along the front of each leg */}
              {[1, -1].map((side) => (
                <mesh key={side} position={[side * 0.13, -0.52, 0.082]} material={mat}>
                  <capsuleGeometry args={[0.026, 0.55, 4, 8]} />
                </mesh>
              ))}
            </>
          )}
        </Region>

        {/* radiation: an ESTIMATE marker (no dosimeter): neutral badge with a dashed edge */}
        <group position={FOCUS.radiation} {...radEvents} name="region-radiation">
          <mesh rotation={[Math.PI / 2, 0, 0]}>
            <cylinderGeometry args={[0.045, 0.045, 0.012, 20]} />
            <meshStandardMaterial
              color={radColor}
              emissive={radColor}
              emissiveIntensity={act('radiation') ? 0.8 : 0.25}
              transparent
              opacity={rad?.status === 'nodata' ? 0.35 : 0.9}
            />
          </mesh>
          <DashedRing radius={0.06} color={radColor} position={[0, 0, 0.012]} />
        </group>

        {/* skin temperature patch on the upper arm; dimmed when its sensor is disconnected */}
        <Region id="temperature" region={regions.temperature} active={act('temperature')} ringRadius={0.08} ringAt={[-0.41, 0.38, 0.08]} {...common}>
          {(mat) => (
            <mesh position={[-0.385, 0.38, 0]} rotation={[0, 0, -0.18]} material={mat}>
              <boxGeometry args={[0.03, 0.1, 0.1]} />
            </mesh>
          )}
        </Region>
        {patch && patch.status !== 'connected' && (
          <mesh position={[-0.41, 0.38, 0.06]} rotation={[0, 0, Math.PI / 4]} raycast={() => null}>
            <boxGeometry args={[0.008, 0.08, 0.008]} />
            <meshBasicMaterial color={theme.danger} />
          </mesh>
        )}

        {/* numbered markers for the sensors worn on the body (from GET /sensors) */}
        {sensors.map(({ sensor, marker }) => (
          <SensorMarker key={sensor.id} sensor={sensor} n={marker!} active={act('sensors')} {...common} />
        ))}
      </group>
    </>
  );
}
