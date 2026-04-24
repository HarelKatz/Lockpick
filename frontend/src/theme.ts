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

export const statusColors: Record<string, string> = {
  entry_point:  '#58a6ff',  // blue (accent)
  compromised:  '#f85149',  // red (danger)
  pivot:        '#d29922',  // orange (warning)
  target:       '#3fb950',  // green (success)
  scoped_out:   '#6e7681',  // gray (muted)
  unreachable:  '#8b949e',  // lighter gray
}


// ── Graph canvas constants (Canvas API cannot read CSS variables) ──────────────
// Confidence edge colors — must match theme.confirmed / observed / indicator
export const CONFIDENCE_CONFIRMED = '#3fb950'  // = theme.confirmed
export const CONFIDENCE_OBSERVED  = '#d29922'  // = theme.observed
export const CONFIDENCE_MUTED     = '#6e7681'  // = theme.indicator / textMuted

// Node fill colors for special states
export const NODE_FILL_HOSTILE  = '#2d1f1f'    // path-highlighted node fill (warm dark)
export const NODE_FILL_FRIENDLY = '#1a2332'    // default node fill (cool dark)

// Node label color
export const NODE_LABEL_COLOR = '#e6edf3'      // slightly brighter than textPrimary for canvas legibility

export const STATUS_LABELS: Record<string, string> = {
  entry_point:  'Entry Point',
  compromised:  'Compromised',
  pivot:        'Pivot',
  target:       'Target',
  scoped_out:   'Scoped Out',
  unreachable:  'Unreachable',
}
