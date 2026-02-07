# Bosdet Labs — Design System

## Brand

- **Name**: Bosdet Labs
- **Vibe**: Clean, confident, minimal. Like a Bloomberg terminal meets a well-designed iOS app.
- **Target user**: Michael — PhD chemist, analytical, values transparency, humble.
- **Tone**: Smart but not showy. Data-forward, not salesy.

## Colors

### Core Palette

| Token            | Hex       | Usage                                 |
| ---------------- | --------- | ------------------------------------- |
| `--bg`           | `#0a0a0a` | Page background (solid, no gradients) |
| `--surface`      | `#111`    | Cards, elevated surfaces              |
| `--surface-alt`  | `#161616` | Hover states, secondary surfaces      |
| `--border`       | `#1e1e1e` | Card borders, dividers                |
| `--border-hover` | `#333`    | Borders on hover/focus                |

### Text

| Token              | Hex       | Usage                       |
| ------------------ | --------- | --------------------------- |
| `--text-primary`   | `#e8e8e8` | Headings, primary content   |
| `--text-secondary` | `#888`    | Labels, supporting text     |
| `--text-muted`     | `#555`    | Placeholders, disabled text |
| `--text-faint`     | `#333`    | Very subtle text (footer)   |

### Accent

| Token           | Hex                     | Usage                              |
| --------------- | ----------------------- | ---------------------------------- |
| `--green`       | `#22c55e`               | Positive values, buy signals, CTAs |
| `--green-muted` | `rgba(34,197,94,0.12)`  | Green backgrounds                  |
| `--red`         | `#ef4444`               | Negative values, warnings          |
| `--red-muted`   | `rgba(239,68,68,0.12)`  | Red backgrounds                    |
| `--amber`       | `#f59e0b`               | Caution, neutral signals           |
| `--amber-muted` | `rgba(245,158,11,0.12)` | Amber backgrounds                  |

### NEVER use

- Gradients on backgrounds (no `linear-gradient` on cards, buttons, body)
- Purple/violet (#a855f7, #6c5ce7) — removed from palette
- Bright saturated green (#00d374) — replaced with softer #22c55e
- Any color with alpha > 0.15 for tinted backgrounds

## Typography

### Font Stack

```
-apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif
```

### Scale

| Name         | Size | Weight | Usage                    |
| ------------ | ---- | ------ | ------------------------ |
| `heading-lg` | 22px | 700    | Page title only          |
| `heading-md` | 17px | 650    | Card titles, stock names |
| `heading-sm` | 14px | 600    | Section labels           |
| `body`       | 14px | 400    | General text             |
| `body-sm`    | 13px | 400    | Secondary info           |
| `caption`    | 11px | 500    | Badges, tags, timestamps |

### Rules

- No ALL CAPS section titles (use sentence case)
- No letter-spacing on headings
- `letter-spacing: 0.02em` only on small caption/tag elements
- Line height: 1.4 for body, 1.2 for headings

## Spacing

| Token        | Value |
| ------------ | ----- |
| `--space-xs` | 4px   |
| `--space-sm` | 8px   |
| `--space-md` | 12px  |
| `--space-lg` | 16px  |
| `--space-xl` | 24px  |

- Card padding: 16px
- Card gap: 10px
- Section gap: 24px
- Border radius: 12px (cards), 8px (badges/chips), 10px (inputs/buttons)

## Components

### Cards

- Background: `var(--surface)` (solid #111, NO gradient)
- Border: `1px solid var(--border)`
- Border radius: 12px
- Hover: `border-color: var(--border-hover)` (desktop only)
- Active: `transform: scale(0.98)` (mobile tap feedback)
- No box-shadow by default

### Buttons

- Primary: `background: var(--green); color: #000; font-weight: 600`
- Secondary: `background: var(--surface); border: 1px solid var(--border); color: var(--text-primary)`
- No gradients. Solid fills.
- Active: `transform: scale(0.97)`
- min-height: 44px (touch target)

### Badges / Chips

- Pill shape: `border-radius: 8px; padding: 4px 10px`
- Positive: `background: var(--green-muted); color: var(--green)`
- Negative: `background: var(--red-muted); color: var(--red)`
- Neutral: `background: #1a1a1a; color: var(--text-secondary)`

### Inputs

- Background: `var(--surface)`
- Border: `1px solid var(--border)`
- Focus: `border-color: var(--green)`
- No glow/shadow on focus
- Placeholder color: `var(--text-muted)`

### Section Headers

- Use `heading-sm` (14px, weight 600)
- Color: `var(--text-secondary)`
- No emojis in section headers
- No uppercase transforms
- Simple text, optional icon as separate element

## Layout Rules

1. Max width: 1000px (not 1200 — tighter is more readable)
2. Mobile-first: single column, 12px gap
3. Tablet (480px+): 2 columns for grids
4. Desktop (768px+): 3 columns, 16px gap
5. No horizontal scrolling ever

## Hooked Model Integration

- **Trigger**: Opening view shows live market movers — immediate curiosity
- **Action**: One tap to analyze any stock. Minimal friction.
- **Variable Reward**: Every stock analysis reveals a score + upside = reward of the hunt
- **Investment**: Saving stocks makes "For You" smarter over time

## Anti-Patterns (NEVER do)

- No gradient backgrounds on any element
- No emoji-heavy section titles (max 1 emoji per section, and only if meaningful)
- No "AI-written" feature lists in headers
- No purple/violet anywhere
- No bright neon green (#00ff00, #00d374)
- No `text-transform: uppercase` on section titles
- No `letter-spacing > 0.5px` on visible text
- No box-shadow on cards in default state
- No animated gradients (except skeleton shimmer for loading)
