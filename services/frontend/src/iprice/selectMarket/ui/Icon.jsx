// Линейные иконки 24 px, линия 1,5 px, как в дизайн-системе iPrice.
const PATHS = {
  home: "M4 11l8-7 8 7v9h-5v-6H9v6H4z",
  table: "M4 5h16v14H4zM4 10h16M10 10v9",
  chart: "M4 20V10M10 20V4M16 20v-8M22 20H2",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  data: "M5 6c0-1.7 3.1-3 7-3s7 1.3 7 3-3.1 3-7 3-7-1.3-7-3zM5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6",
  check: "M5 12.5l4.5 4.5L19 7.5",
  x: "M6 6l12 12M18 6L6 18",
  alert: "M12 3l10 17H2zM12 10v4M12 17v.5",
  info: "M12 21a9 9 0 100-18 9 9 0 000 18zM12 11v6M12 7.5v.5",
  up: "M12 19V5M6 11l6-6 6 6",
  down: "M12 5v14M6 13l6 6 6-6",
  approx: "M4 9c2.5-2.5 5-2.5 8 0s5.5 2.5 8 0M4 15c2.5-2.5 5-2.5 8 0s5.5 2.5 8 0",
  minus: "M6 12h12",
  dot: "M12 13a1 1 0 100-2 1 1 0 000 2z",
  search: "M11 17.5a6.5 6.5 0 100-13 6.5 6.5 0 000 13zM20 20l-4.3-4.3",
  filter: "M3 5h18l-7 8v6l-4 2v-8z",
  chev: "M9 6l6 6-6 6",
  chevDown: "M6 9l6 6 6-6",
  chevLeft: "M15 6l-6 6 6 6",
  download: "M12 4v12M7 11l5 5 5-5M4 20h16",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v4h16v-4",
  play: "M7 5l12 7-12 7z",
  refresh: "M20 12a8 8 0 01-14 5.3M4 12A8 8 0 0118 6.7M18 3v4h-4M6 21v-4h4",
  edit: "M4 20h4L19 9l-4-4L4 16zM13 7l4 4",
  history: "M12 21a9 9 0 10-9-9M3 4v5h5M12 7v5l3 2",
  ext: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  settings: "M12 15a3 3 0 100-6 3 3 0 000 6zM12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1",
  compare: "M8 3v18M16 3v18M3 8h5M16 16h5M3 16h5M16 8h5",
  star: "M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7z",
  flag: "M5 21V4M5 4h11l-2 4 2 4H5",
  lock: "M5 11h14v9H5zM8 11V8a4 4 0 018 0v3",
  tag: "M3 12V4h8l10 10-8 8zM7.5 8.5h.01",
  bolt: "M13 2L4 14h7l-1 8 9-12h-7z",
  user: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21a8 8 0 0116 0",
  plus: "M12 5v14M5 12h14",
  eye: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 100-6 3 3 0 000 6z",
  eyeOff: "M3 3l18 18M10.6 6.1A10 10 0 0112 6c6.5 0 10 6 10 6a17 17 0 01-3.2 3.9M6.1 7.6C3.6 9.4 2 12 2 12s3.5 7 10 7c1.6 0 3-.4 4.3-1",
  pin: "M15 3l6 6-3 1-4 4 .5 5L4.5 9.5l5 .5 4-4z",
  route: "M6 19a2 2 0 100-4 2 2 0 000 4zM18 9a2 2 0 100-4 2 2 0 000 4zM6 15V9a3 3 0 013-3h7M18 9v6a3 3 0 01-3 3H8",
  logout: "M9 4H5v16h4M14 8l4 4-4 4M18 12H9",
  help: "M12 21a9 9 0 100-18 9 9 0 000 18zM9.5 9.3a2.5 2.5 0 114.2 1.8c-.9.7-1.7 1.2-1.7 2.6M12 17v.5",
  wallet: "M4 7h15v12H4zM4 7l11-3v3M15 13h2",
  box: "M3 8l9-5 9 5v8l-9 5-9-5zM3 8l9 5 9-5M12 13v8",
};

export default function Icon({ name, size, className = "", title, style }) {
  const d = PATHS[name] || PATHS.dot;
  return (
    <svg
      className={`ip-i ${className}`}
      viewBox="0 0 24 24"
      width={size}
      height={size}
      style={size ? { width: size, height: size, ...style } : style}
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
    >
      {title ? <title>{title}</title> : null}
      <path d={d} />
    </svg>
  );
}

// Знак iPrice: ценник со знаком рубля.
export function Mark({ size = 28 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <rect width="32" height="32" rx="8" fill="#E1EDF8" />
      <polygon points="6,16 12,9 26,9 26,23 12,23" fill="#3F72AA" stroke="#3F72AA" strokeWidth="2" strokeLinejoin="round" />
      <circle cx="10.4" cy="16" r="1.8" fill="#F39F63" />
      <path d="M17.5 20.6V11.5H20.5A2.5 2.5 0 0 1 20.5 16.5H16M16 18.6H21.2" fill="none" stroke="#E1EDF8" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
