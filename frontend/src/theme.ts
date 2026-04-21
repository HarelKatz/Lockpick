/**
 * Dark theme CSS custom properties for Lockpick.
 * Inspired by GitHub dark theme palette.
 */
export const theme = {
  // Base colors
  bgBase: '#0d1117',       // Page background
  bgSurface: '#161b22',    // Cards, modals, panels
  bgSurface2: '#1c2128',   // Secondary surfaces (hover, inputs)
  bgSurface3: '#21262d',   // Tertiary surfaces

  // Borders
  border: '#30363d',
  borderSubtle: '#21262d',

  // Text
  textPrimary: '#c9d1d9',
  textSecondary: '#8b949e',
  textMuted: '#6e7681',
  textInverse: '#0d1117',

  // Accent / interactive
  accent: '#58a6ff',
  accentHover: '#79c0ff',
  accentSubtle: '#1f2937',

  // Status colors
  success: '#3fb950',
  warning: '#d29922',
  danger: '#f85149',
  dangerHover: '#ff7b72',

  // Confidence colors (for graph edges)
  confirmed: '#3fb950',    // green
  observed: '#d29922',     // orange
  indicator: '#6e7681',    // gray
} as const

export type ThemeColor = keyof typeof theme

/** Colors for host status tags (Phase 11). */
export const statusColors: Record<string, string> = {
  entry_point:  '#58a6ff',  // blue
  compromised:  '#f85149',  // red
  pivot:        '#d29922',  // orange
  target:       '#bc8cff',  // purple
  scoped_out:   '#3fb950',  // green
  unreachable:  '#6e7681',  // gray
}

/** Human-readable labels for host status values. */
export const STATUS_LABELS: Record<string, string> = {
  entry_point:  'Entry Point',
  compromised:  'Compromised',
  pivot:        'Pivot',
  target:       'Target',
  scoped_out:   'Scoped Out',
  unreachable:  'Unreachable',
}
