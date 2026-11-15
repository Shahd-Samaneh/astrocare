// The 3D view: canvas, lights, orbit controls (from three/examples, no drei), camera easing,
// keyboard controls and the hover tooltip.
//
// Performance: dpr capped at 2, low-poly primitives, no MSAA, animation through refs in useFrame.
// Rendering is on demand: the idle float/pulse requests 30 fps only while the tab is visible, the
// canvas is in view and motion is allowed; otherwise a frame is drawn only after a control change,
// a camera move or new data. A hidden tab renders nothing (frameloop "never"). Measured with the
// local model running: see docs/twin-notes.md.
import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber';
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from 'react';
import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import type { TwinTheme } from '../env';
import type { RegionId, TwinRegion } from '../types';
import { REGION_SHORT } from '../twinView';
import { Astronaut } from './Astronaut';
import { FOCUS, VIEW_DIR } from './layout';
import styles from './TwinCanvas.module.css';

const HOME_POS = new THREE.Vector3(0, 0.25, 3.4);
const HOME_TARGET = new THREE.Vector3(0, -0.02, 0);
const MIN_DIST = 1.1;
const MAX_DIST = 6;
const FOCUS_DIST = 1.45;
/** Idle animation (float, heart pulse) frame rate. The loop is on demand, so a still scene costs
 *  nothing; 30 fps is plenty for a slow bob and keeps the CPU/GPU free for the local model. */
const IDLE_FPS = 30;

/** Requests a frame IDLE_FPS times a second while the idle animation should run. */
function Ticker({ running }: { running: boolean }) {
  const { invalidate } = useThree();
  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => invalidate(), 1000 / IDLE_FPS);
    return () => window.clearInterval(id);
  }, [running, invalidate]);
  return null;
}

export interface TwinCanvasHandle {
  reset: () => void;
}

interface RigApi {
  focus: (id: RegionId | null) => void;
  rotate: (dAzimuth: number, dPolar: number) => void;
  zoom: (factor: number) => void;
}

interface RigProps {
  reducedMotion: boolean;
  apiRef: React.MutableRefObject<RigApi | null>;
}

/** Orbit controls + eased camera moves. */
function CameraRig({ reducedMotion, apiRef }: RigProps) {
  const { camera, gl, invalidate } = useThree();
  const controls = useRef<OrbitControls>();
  const goal = useRef<{ pos: THREE.Vector3; target: THREE.Vector3 } | null>(null);

  useEffect(() => {
    const c = new OrbitControls(camera, gl.domElement);
    c.enablePan = false;
    c.minDistance = MIN_DIST;
    c.maxDistance = MAX_DIST;
    c.enableDamping = !reducedMotion;
    c.dampingFactor = 0.08;
    c.rotateSpeed = 0.7;
    c.zoomSpeed = 0.8;
    c.target.copy(HOME_TARGET);
    c.update();
    const cancel = () => (goal.current = null); // the user took over: stop easing
    const change = () => invalidate();
    c.addEventListener('start', cancel);
    c.addEventListener('change', change);
    controls.current = c;
    return () => {
      c.removeEventListener('start', cancel);
      c.removeEventListener('change', change);
      c.dispose();
    };
  }, [camera, gl, invalidate, reducedMotion]);

  const moveTo = useCallback(
    (pos: THREE.Vector3, target: THREE.Vector3) => {
      const c = controls.current;
      if (!c) return;
      if (reducedMotion) {
        goal.current = null;
        camera.position.copy(pos);
        c.target.copy(target);
        c.update();
      } else {
        goal.current = { pos, target };
      }
      invalidate();
    },
    [camera, invalidate, reducedMotion],
  );

  useEffect(() => {
    apiRef.current = {
      focus: (id) => {
        if (id === null) return moveTo(HOME_POS.clone(), HOME_TARGET.clone());
        const target = new THREE.Vector3(...FOCUS[id]);
        const dir = new THREE.Vector3(...(VIEW_DIR[id] ?? [0, 0.12, 1])).normalize();
        moveTo(target.clone().addScaledVector(dir, FOCUS_DIST), target);
      },
      rotate: (dAz, dPol) => {
        const c = controls.current;
        if (!c) return;
        goal.current = null;
        const offset = camera.position.clone().sub(c.target);
        const s = new THREE.Spherical().setFromVector3(offset);
        s.theta += dAz;
        s.phi = THREE.MathUtils.clamp(s.phi + dPol, 0.15, Math.PI - 0.15);
        camera.position.copy(c.target).add(new THREE.Vector3().setFromSpherical(s));
        c.update();
        invalidate();
      },
      zoom: (f) => {
        const c = controls.current;
        if (!c) return;
        goal.current = null;
        const offset = camera.position.clone().sub(c.target);
        offset.setLength(THREE.MathUtils.clamp(offset.length() * f, MIN_DIST, MAX_DIST));
        camera.position.copy(c.target).add(offset);
        c.update();
        invalidate();
      },
    };
    return () => {
      apiRef.current = null;
    };
  }, [apiRef, camera, invalidate, moveTo]);

  useFrame((_, dt) => {
    const c = controls.current;
    if (!c) return;
    const g = goal.current;
    if (g) {
      const k = 1 - Math.exp(-Math.min(dt, 0.1) * 4);
      camera.position.lerp(g.pos, k);
      c.target.lerp(g.target, k);
      if (camera.position.distanceTo(g.pos) < 0.002 && c.target.distanceTo(g.target) < 0.002) goal.current = null;
      else invalidate();
    }
    c.update();
  });
  return null;
}

export interface TwinCanvasProps {
  regions: TwinRegion[];
  theme: TwinTheme;
  selected: RegionId | null;
  reducedMotion: boolean;
  visible: boolean;
  onSelect: (id: RegionId) => void;
  /** Lost WebGL context or a render error: the page switches to the list view. */
  onFail: () => void;
}

interface Tip {
  id: RegionId;
  x: number;
  y: number;
}

export const TwinCanvas = forwardRef<TwinCanvasHandle, TwinCanvasProps>(function TwinCanvas(
  { regions, theme, selected, reducedMotion, visible, onSelect, onFail },
  ref,
) {
  const wrap = useRef<HTMLDivElement>(null);
  const rig = useRef<RigApi | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [inView, setInView] = useState(true);
  // Unmounting the canvas (e.g. switching to the list view) disposes the renderer, which fires
  // "webglcontextlost" on purpose: only a context lost while still mounted is a real failure.
  const alive = useRef(true);
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const byId = Object.fromEntries(regions.map((r) => [r.id, r])) as Partial<Record<RegionId, TwinRegion>>;

  useImperativeHandle(ref, () => ({ reset: () => rig.current?.focus(null) }), []);

  // Stop the idle animation while the canvas is scrolled out of view.
  useEffect(() => {
    const el = wrap.current;
    if (!el || typeof IntersectionObserver === 'undefined') return;
    const io = new IntersectionObserver(([entry]) => setInView(entry.isIntersecting), { threshold: 0.05 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  // Ease toward the selected region (or back home when deselected).
  useEffect(() => {
    rig.current?.focus(selected);
  }, [selected]);

  const onHover = useCallback((id: RegionId | null, e?: ThreeEvent<PointerEvent>) => {
    const box = wrap.current?.getBoundingClientRect();
    if (!id || !e || !box) return setTip(null);
    setTip({ id, x: e.nativeEvent.clientX - box.left, y: e.nativeEvent.clientY - box.top });
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    const r = rig.current;
    if (!r) return;
    const step = Math.PI / 12;
    const keys: Record<string, () => void> = {
      ArrowLeft: () => r.rotate(-step, 0),
      ArrowRight: () => r.rotate(step, 0),
      ArrowUp: () => r.rotate(0, -step / 2),
      ArrowDown: () => r.rotate(0, step / 2),
      '+': () => r.zoom(0.85),
      '=': () => r.zoom(0.85),
      '-': () => r.zoom(1.18),
      Home: () => r.focus(null),
    };
    const fn = keys[e.key];
    if (fn) {
      e.preventDefault();
      fn();
    }
  };

  const hovered = tip?.id ?? null;
  const tipRegion = tip ? byId[tip.id] : undefined;
  // Hidden tab: no rendering at all. Otherwise frames are rendered on demand only: by the idle
  // ticker (30 fps, motion allowed and canvas in view), camera moves, controls and data changes.
  const frameloop = visible ? 'demand' : 'never';
  const animate = visible && inView && !reducedMotion;
  const summary = regions.map((r) => `${REGION_SHORT[r.id]}: ${r.headline}`).join('. ');

  return (
    <div
      ref={wrap}
      className={styles.wrap}
      style={{ cursor: hovered ? 'pointer' : 'grab' }}
      tabIndex={0}
      role="application"
      aria-roledescription="3D view"
      aria-label="Digital twin 3D view. Arrow keys rotate, plus and minus zoom, Home resets. Select a region from the list beside the view."
      aria-describedby="twin-3d-summary"
      onKeyDown={onKeyDown}
      onPointerLeave={() => setTip(null)}
    >
      <p id="twin-3d-summary" className="sr-only">
        {summary}
      </p>
      <Canvas
        dpr={[1, 2]}
        frameloop={frameloop}
        camera={{ position: HOME_POS.toArray(), fov: 40, near: 0.05, far: 100 }}
        gl={{ antialias: false, powerPreference: 'low-power' }}
        onCreated={({ gl }) => {
          gl.domElement.addEventListener('webglcontextlost', (ev) => {
            ev.preventDefault();
            window.setTimeout(() => {
              if (alive.current) onFail();
            }, 0);
          });
        }}
        onPointerMissed={() => setTip(null)}
      >
        <color attach="background" args={[theme.background]} />
        <ambientLight intensity={0.45} color={theme.star} />
        <directionalLight position={[1.5, 2.5, 3]} intensity={1.1} color={theme.star} />
        {/* soft blue rim light from behind */}
        <directionalLight position={[-1.5, 1.2, -3]} intensity={2.2} color={theme.rim} />
        <pointLight position={[0, 0.3, -1.2]} intensity={1.2} distance={3} color={theme.rim} />
        <Astronaut
          regions={byId}
          theme={theme}
          selected={selected}
          hovered={hovered}
          reducedMotion={reducedMotion}
          onHover={onHover}
          onSelect={onSelect}
        />
        <CameraRig reducedMotion={reducedMotion} apiRef={rig} />
        <Ticker running={animate} />
      </Canvas>
      {tip && tipRegion && (
        <div className={styles.tip} style={{ left: tip.x, top: tip.y }} role="tooltip">
          <strong>{tipRegion.label}</strong>
          <span>{tipRegion.headline}</span>
        </div>
      )}
    </div>
  );
});
