// Browser environment for the twin: theme tokens, WebGL support, reduced motion, tab visibility.
import { useEffect, useState } from 'react';
import type { TwinStatus } from './types';
import { STATUS_TOKEN } from './twinView';

export interface TwinTheme {
  status: Record<TwinStatus, string>;
  background: string;
  suit: string;
  suitShade: string;
  visor: string;
  rim: string;
  star: string;
  neutral: string;
  danger: string;
  ok: string;
}

function token(style: CSSStyleDeclaration, name: string, fallbackName: string): string {
  // Fallback is another token name, never a raw colour: if both are empty three.js gets white.
  return (style.getPropertyValue(name) || style.getPropertyValue(fallbackName)).trim() || '#ffffff';
}

/** Read the design tokens from CSS variables at runtime, so the 3D colours match the theme. */
export function readTheme(el: Element = document.documentElement): TwinTheme {
  const s = getComputedStyle(el);
  const status = Object.fromEntries(
    Object.entries(STATUS_TOKEN).map(([k, v]) => [k, token(s, v, '--text-faint')]),
  ) as Record<TwinStatus, string>;
  return {
    status,
    background: token(s, '--bg-app', '--bg-nav'),
    suit: token(s, '--text-2', '--text'),
    suitShade: token(s, '--text-muted', '--text-2'),
    visor: token(s, '--bg-nav', '--bg-app'),
    rim: token(s, '--accent', '--accent-2'),
    star: token(s, '--text', '--text-2'),
    neutral: token(s, '--text-muted', '--text-faint'),
    danger: token(s, '--danger', '--warn'),
    ok: token(s, '--ok', '--accent'),
  };
}

export function hasWebGL(): boolean {
  try {
    const c = document.createElement('canvas');
    return !!(window.WebGLRenderingContext && (c.getContext('webgl2') || c.getContext('webgl')));
  } catch {
    return false;
  }
}

function useMedia(query: string): boolean {
  const [match, setMatch] = useState(() => typeof window !== 'undefined' && window.matchMedia(query).matches);
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setMatch(m.matches);
    on();
    m.addEventListener('change', on);
    return () => m.removeEventListener('change', on);
  }, [query]);
  return match;
}

export const useReducedMotion = () => useMedia('(prefers-reduced-motion: reduce)');

/** False while the browser tab is hidden (the render loop pauses). */
export function usePageVisible(): boolean {
  const [visible, setVisible] = useState(() => typeof document === 'undefined' || !document.hidden);
  useEffect(() => {
    const on = () => setVisible(!document.hidden);
    document.addEventListener('visibilitychange', on);
    return () => document.removeEventListener('visibilitychange', on);
  }, []);
  return visible;
}
