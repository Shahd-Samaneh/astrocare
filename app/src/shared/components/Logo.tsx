// AstroCare mark: a planet with a ring and a pink medical cross. Inline SVG, no external file.
//   <Logo size={32} />
export function Logo({ size = 32, title }: { size?: number; title?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      role={title ? 'img' : undefined}
      aria-hidden={title ? undefined : true}
      aria-label={title}
    >
      <circle cx="16" cy="16" r="9" fill="var(--bg-active)" stroke="var(--accent)" strokeWidth="2" />
      <ellipse
        cx="16"
        cy="16"
        rx="15"
        ry="5"
        transform="rotate(-20 16 16)"
        stroke="var(--accent-2)"
        strokeWidth="1.6"
        strokeDasharray="30 6"
      />
      <path d="M14.5 11.5h3v3h3v3h-3v3h-3v-3h-3v-3h3z" fill="var(--pink)" />
    </svg>
  );
}
