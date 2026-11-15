// Where each body region sits on the astronaut (the astronaut faces +z, so its left is +x).
import type { RegionId } from '../types';

export const FOCUS: Record<RegionId, [number, number, number]> = {
  brain: [0, 0.86, 0],
  eyes: [0, 0.78, 0.28],
  heart: [0.03, 0.31, 0.23],
  lungs: [0, 0.36, 0.2],
  bones: [0, -0.2, 0.05],
  radiation: [-0.13, 0.12, 0.21],
  temperature: [-0.39, 0.38, 0],
  sensors: [0, 0.1, 0.2],
};
/** Direction the camera looks from when a region is selected. */
export const VIEW_DIR: Partial<Record<RegionId, [number, number, number]>> = {
  temperature: [-1, 0.15, 0.7],
  brain: [0.5, 0.35, 1],
  bones: [0.35, 0.1, 1],
};

