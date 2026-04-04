# Amplifier Admin Dashboard — Design System

## 1. Color Palette

### Backgrounds
| Token | Hex | Usage |
|-------|-----|-------|
| Surface | `#0f172a` | Page background, form inputs |
| Sidebar | `linear-gradient(180deg, #1e293b, #172032)` | Left navigation |
| Card | `linear-gradient(145deg, #1e293b, #1a2332)` | Content cards, stat boxes |
| Card hover | Shadow: `0 6px 20px rgba(0,0,0,0.25)` | Card lift effect |

### Text
| Token | Hex | Usage |
|-------|-----|-------|
| Primary | `#f8fafc` | Headings, strong text |
| Body | `#e2e8f0` | Paragraphs, table cells |
| Secondary | `#94a3b8` | Labels, nav items, captions |
| Muted | `#64748b` | Hints, disabled text, table headers |

### Borders
| Token | Hex | Usage |
|-------|-----|-------|
| Default | `#334155` | Card borders, dividers, table rows |
| Active | `#2563eb` | Active sidebar item, focus rings |

### Accent Colors
| Token | Hex | Usage |
|-------|-----|-------|
| Primary | `#2563eb` | Buttons, active nav, links |
| Primary hover | `#1d4ed8` | Button hover state |
| Success | `#22c55e` | Success buttons, positive values |
| Danger | `#ef4444` | Danger buttons, errors, red badges |
| Warning | `#facc15` | Warning values, yellow badges |
| Info | `#60a5fa` | Links, info text |

---

## 2. Typography

### Font
- **Family:** `'DM Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Source:** Google Fonts (variable weight 400-700)

### Scale
| Element | Size | Weight | Color |
|---------|------|--------|-------|
| Page heading (h1) | 26px | 700 | Gradient `#f8fafc → #94a3b8` |
| Card title | 16px | 700 | `#f8fafc` |
| Stat value | 26px | 700 | `#3b82f6` (or variant) |
| Stat label | 12px | 500 | `#64748b` |
| Table header | 11px | 600 | `#64748b` uppercase |
| Table cell | 14px | 400 | `#cbd5e1` |
| Body text | 14px | 400 | `#e2e8f0` |
| Badge | 12px | 500 | Per-badge color |
| Nav item | 14px | 400/500 | `#94a3b8` / `#f8fafc` (active) |
| Form label | 13px | 500 | `#94a3b8` |
| Form input | 14px | 400 | `#e2e8f0` |

---

## 3. Components

### Badges
```css
.badge { padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 500; }
```
| Class | Background | Text | Usage |
|-------|-----------|------|-------|
| `.badge-green` | `#14532d` | `#86efac` | Active, live, paid, approved |
| `.badge-blue` | `#1e3a5f` | `#93bbfd` | Posted, accepted, platform names |
| `.badge-yellow` | `#713f12` | `#fde68a` | Pending, suspended, paused |
| `.badge-red` | `#7f1d1d` | `#fca5a5` | Banned, flagged, deleted, cancelled |
| `.badge-gray` | `#334155` | `#94a3b8` | Draft, neutral, mode |

### Buttons
```css
.btn { padding: 8px 16px; border-radius: 8px; font-size: 14px; font-weight: 600; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
```
| Class | Background | Hover Effect |
|-------|-----------|-------------|
| `.btn-primary` | `#2563eb` | Shadow `rgba(37,99,235,0.35)` |
| `.btn-success` | `#22c55e` | Shadow `rgba(34,197,94,0.3)` |
| `.btn-danger` | `#ef4444` | Shadow `rgba(239,68,68,0.3)` |
| `.btn-secondary` | `#334155` | Background `#3d4f68` |

### Stat Cards
```css
.stat { padding: 16px 24px; border-radius: 12px; min-width: 160px; flex: 1; }
.stat-val { font-size: 26px; font-weight: 700; color: #3b82f6; }
```
Color variants: `.stat-val.green` (`#4ade80`), `.stat-val.yellow` (`#facc15`), `.stat-val.red` (`#f87171`)

### Content Cards
```css
.card { border-radius: 12px; padding: 20px; border: 1px solid #334155; }
```
Hover: `translateY(-1px)` with shadow

### Tables
```css
th { font-size: 11px; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; }
td { font-size: 14px; color: #cbd5e1; }
tr:hover td { background: rgba(37, 99, 235, 0.04); }
tr:hover td:first-child { box-shadow: inset 3px 0 0 #2563eb; }
```

### Trust Bar
```css
.trust-bar { height: 6px; background: #334155; border-radius: 3px; }
.trust-fill { height: 100%; border-radius: 3px; }
```
Colors: `#22c55e` (score >= 70), `#facc15` (>= 40), `#ef4444` (< 40)

### Form Controls
```css
.form-control { padding: 10px 14px; background: #0f172a; border: 1px solid #334155; border-radius: 8px; }
.form-control:focus { border-color: #2563eb; box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1); }
```

### Alerts
```css
.alert { padding: 12px 16px; border-radius: 8px; font-size: 14px; }
```
| Class | Background | Text | Border |
|-------|-----------|------|--------|
| `.alert-success` | `#14532d` | `#86efac` | `#166534` |
| `.alert-error` | `#7f1d1d` | `#fca5a5` | `#991b1b` |
| `.alert-info` | `#1e3a5f` | `#93bbfd` | `#1e40af` |

---

## 4. Layout

### Page Structure
```
┌──────────┬────────────────────────────────────────┐
│          │                                        │
│ Sidebar  │  Main Content                         │
│ (240px)  │  (flex: 1, padding: 24px 32px)        │
│ fixed    │                                        │
│          │  ┌─ Page Header ───────────────────┐  │
│ Brand    │  │ h1 Title          Action Button  │  │
│ Nav      │  └─────────────────────────────────┘  │
│ Items    │                                        │
│          │  ┌─ Stats Row ─────────────────────┐  │
│          │  │ [Stat] [Stat] [Stat] [Stat]     │  │
│          │  └─────────────────────────────────┘  │
│          │                                        │
│          │  ┌─ Card ──────────────────────────┐  │
│          │  │ Card Title                       │  │
│          │  │ ┌─ Table ───────────────────┐   │  │
│ Account  │  │ │ th  th  th  th            │   │  │
│ ──────   │  │ │ td  td  td  td            │   │  │
│ Logout   │  │ └───────────────────────────┘   │  │
│          │  │ ┌─ Pagination ──────────────┐   │  │
│          │  │ │ Page 1 of 5    [Prev][Next]│   │  │
│          │  │ └───────────────────────────┘   │  │
│          │  └─────────────────────────────────┘  │
│          │                                        │
└──────────┴────────────────────────────────────────┘
```

### Responsive Breakpoints
- **>768px**: Full sidebar + main content
- **<=768px**: Sidebar hidden, main content full-width, stats stack vertically

---

## 5. Icons

All icons are inline SVGs from [Heroicons](https://heroicons.com/) (outline style, 16x16, stroke-width 1.5).

| Icon | Page |
|------|------|
| Bar chart | Overview |
| Users group | Users |
| Building | Companies |
| Megaphone | Campaigns |
| Banknote | Financial |
| Shield | Fraud & Trust |
| Chart squares | Analytics |
| Warning triangle | Review Queue |
| Gear | Settings |
| Document | Audit Log |
| Arrow right | Logout |

---

## 6. Interactive Patterns

### Clickable Table Rows
List tables have `cursor: pointer` and `onclick` handlers that navigate to detail pages. The blue left-border glow on hover reinforces this affordance.

### Auto-Submit Dropdowns
Filter and sort dropdowns include `onchange="this.form.submit()"` for instant filtering without clicking a button.

### Tab Switching
Detail pages use JavaScript tabs. Clicking a tab button:
1. Removes `.active` from all `.tab` and `.tab-content` elements
2. Adds `.active` to the clicked tab and corresponding content div

### Expandable Details
Financial transaction breakdowns use a `onclick` toggle that shows/hides a sibling div.

### Confirmation Dialogs
Destructive actions (ban, cancel, deduct funds, reject) use `onclick="return confirm('...')"` to prevent accidental execution.

---

## 7. Status Color Mapping

| Entity | Value | Badge Color |
|--------|-------|-------------|
| User status | active | green |
| User status | suspended | yellow |
| User status | banned | red |
| Company status | active | green |
| Company status | suspended | red |
| Campaign status | active | green |
| Campaign status | paused | yellow |
| Campaign status | completed | blue |
| Campaign status | cancelled | red |
| Campaign status | draft | gray |
| Screening status | approved | green |
| Screening status | flagged | red |
| Screening status | rejected | red |
| Screening status | pending | yellow |
| Post status | live | green |
| Post status | deleted/flagged | red |
| Payout status | paid | green |
| Payout status | pending | yellow |
| Payout status | processing | blue |
| Payout status | failed | red |
| Assignment status | paid/posted | green |
| Assignment status | accepted | blue |
| Assignment status | pending_invitation | yellow |
| Assignment status | rejected/expired | red |
| Appeal result | upheld | green |
| Appeal result | denied | red |
| Appeal result | pending | yellow |
