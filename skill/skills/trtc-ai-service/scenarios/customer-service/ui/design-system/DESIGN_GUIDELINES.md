# Design Guidelines (DESIGN_GUIDELINES)

> Scope: All UIs under `scenarios/customer-service/` (voice-customer-service, admin-board).
>
> Origin: `voice_ai_customer_service (3).html` prototype design, v2.0.0 (light / glassmorphism / purple-pink gradient).

---

## 1. Theme & Background

| Category | Rule |
|---|---|
| **Theme** | Light theme (light mode), no dark mode toggle |
| **Background** | Multi-layer radial gradient overlay (soft purple + light pink + pale blue), base `#f7f3ff` |
| **Panels** | Glassmorphism panels (`glass` class): `backdrop-filter: blur(22px) saturate(140%)` |

## 2. Color Spec

### 2.1 Palette

Full expansion: CSS variables (defined in `tokens.css`, compiled from `design_tokens.json`)
Grouped by namespace:

```
Foreground / Text
  --foreground : #1a1530     Primary text color (deep purple-black)
  --muted      : #6b6580     Secondary/auxiliary text

Cards / Panels
  --card        : rgba(255,255,255,0.55)   Glass panel background
  --card-strong : rgba(255,255,255,0.78)   Strong glass panel
  --card-border : rgba(255,255,255,0.85)   Panel stroke

Brand / Accent
  --primary : #9b7bf7       Primary purple (gradient start)
  --pink    : #f7b7d4       Pink (gradient end)
  --blue    : #7ba8f7       Auxiliary blue
  --accent-grad : linear-gradient(135deg, #9b7bf7 0%, #f7b7d4 100%)

Status Colors
  --green : #34c77b         Success / Online / Connected
  --red   : #ff5c7a         Error / Hang up / Muted
```

> **Two variable namespaces, one palette.** The customer widget uses the short names
> above (defined in its own `styles.css :root`). The admin board uses the long-form
> `--color-*` namespace (defined in `tokens.css`). Both resolve to the SAME light
> purple-pink glassmorphism palette. `tokens.css` is the canonical design-variable
> file and now ships the light palette directly (no dark override anywhere):
>
> ```
> tokens.css (--color-* namespace, shared by admin; light palette)
>   --color-bg-gradient        multi-radial ambient, base #f7f3ff   (= .bg-ambient)
>   --color-bg-surface         rgba(255,255,255,0.55)               (= --card)
>   --color-bg-surface-strong  rgba(255,255,255,0.82)               (= --card-strong)
>   --color-bg-border          rgba(155,123,247,0.18)               (purple-tinted stroke)
>   --color-brand-accent       #9b7bf7                              (= --primary)
>   --color-text-primary       #1a1530                              (= --foreground)
>   --color-text-secondary     #6b6580                              (= --muted)
>   --color-status-success     #1f8e57   info #3b6bcf
>   --color-status-warning     #c46500   error #d6476b              (darkened for light bg)
>   --font-family-base         Inter, 'SF Pro Display', system-ui, sans-serif
> ```

**Correct usage**:
```css
.my-button {
  background: var(--accent-grad);
  color: white;
}
.badge-success {
  background: rgba(52,199,123,0.15);
  color: var(--green);
}
```

**Forbidden usage**:
```css
.my-button {
  background: linear-gradient(135deg, #9b7bf7, #f7b7d4);   /* should reference --accent-grad */
}
```

### 2.2 Tailwind Integration

The prototype uses Tailwind CSS CDN; custom colors are injected in `tailwind.config`:

```js
tailwind.config = {
  theme: { extend: {
    colors: { ink:'#1a1530', muted:'#6b6580', primary:'#9b7bf7', pink:'#f7b7d4', blue2:'#7ba8f7' },
    fontFamily: { sans: ['Inter','SF Pro Display','system-ui','sans-serif'] }
  } }
}
```

> **Note**: Tailwind class names (e.g., `text-ink`, `text-muted`, `bg-primary`) map to the above CSS variable names but belong to **two independent naming systems**. For new UIs, prefer Tailwind classes for layout, and CSS variables from `styles.css` for core styling.

---

## 3. Layout Spec

### 3.1 Overall Layout

```
+----------------------------------------------------------+
|  HEADER: logo + connection status indicators              |
+----------------------------------------------------------+
|  SIDEBAR (300px)        |  MAIN CONSOLE (flex:1)          |
|  - Products / Orders    |  - Orb breathing ball           |
|    tab bar               |  - Status text (Ready/Listening/…) |
|  - Search box            |  - Large waveform animation    |
|  - Card list (scrollable)|  - Dock control bar            |
|                          |  - IM chat drawer              |
+----------------------------------------------------------+
|  FOOTER                                                  |
+----------------------------------------------------------+
```

### 3.2 Responsive Breakpoints

| Breakpoint | Layout |
|---|---|
| `≥ 1024px` (lg) | Two-column: `grid-cols-[300px,1fr]`, fixed height 620px |
| `< 1024px` | Sidebar shrinks to `max-height: 50vh`, main panel auto-fills height |

---

## 4. Component Spec

### 4.1 Orb Breathing Ball

- **Position**: Centered in main console
- **Size**: 160×160px (200×200px when ≥760px)
- **Style**: Multi-layer gradient circle + `inset` shadow simulating glass texture + highlight dot
- **Animation**:
  | State | Animation | Period |
  |---|---|---|
  | idle | `breathe` | 4.5s |
  | listening | `breathe` | 1.2s |
  | speaking | `breathe` | 0.7s |
- **Halos**: 3 layers of `orb-halo`, animation delays 0 / 1.1s / 2.2s, expanding from scale(0.85) to scale(1.7) and fading out

### 4.2 Large Waveform (wave-big)

- **Position**: Below the Orb
- **Size**: width `min(520px, 90%)`, height 80px
- **Composition**: 32 vertical bars, `background: linear-gradient(180deg, #9b7bf7, #f7b7d4)`
- **Animation**:
  | State | Animation | Period |
  |---|---|---|
  | idle | Paused, height fixed 10px, opacity 0.4 | — |
  | listening | `wv` | 0.7s |
  | speaking | `wv` | 0.5s |

### 4.3 Dock Control Bar

**Collapsed state**: Single green circular Start button, 58×58px

**Expanded state** (after Start):
- Glassmorphism pill container (`border-radius: 999px`)
- Contains 3 buttons:
  | Button | Icon | Style |
  |---|---|---|
  | Microphone | `mic` / `mic-off` | Rounded 46×46px, white background; red gradient when muted |
  | Human Support | `headphones` + "Human Support" | Blue gradient background + white text |
  | Hang up | `phone-off` | Circle 46×46px, red gradient background |

**Transition animation**: Start button shrinks and disappears (`scale(0.4)`), expanded bar pops in from `scale(0.6)`

### 4.4 Knowledge Base Sidebar (KB Sidebar)

- **Tab switching**: Products / Orders, `kb-tabs` container
- **Search box**: Search icon, rounded input
- **Product cards**:
  - Thumbnail 52×52px + name + price + tag (Hot / In stock / Low stock)
  - Hover: lifts 2px + shadow enhancement
- **Order cards**:
  - Order number + date + status badge + product thumbnail 38×38px

### 4.5 Detail View

- Layout switches after clicking a product/order card:
  - Top compact bar (back button + mini Orb + waveform)
  - Center: question text + detail card
  - Bottom: expanded Dock
- **Product detail card**: Large image 140×140px + name + rating + description + price + add-to-cart button
- **Order detail card**: Order number + date + status + product thumbnail 64×64px + total

### 4.6 IM Chat Drawer

- **Position**: Floating at bottom-right, `position: absolute; right: 18px; bottom: 90px`
- **Size**: width 360px, `max-width: calc(100% - 36px)`
- **Structure**: Title bar + message list (max-height: 280px) + input bar
- **Bubble styles**:
  - AI bubble: White background, top-left corner cut
  - User bubble: Purple gradient background, white text, top-right corner cut
  - System bubble: Semi-transparent white background, italic centered, pill-shaped
- **Typing indicator**: 3 bouncing dots

### 4.7 Queue Progress Bar

- Shown below the Orb after initiating handoff
- Progress bar: `background: var(--accent-grad)` filling over a white base
- Timer: updates every minute with formatted time (`0:00` → `0:08`)

### 4.8 Toast Notifications

- Clicking a card when not connected → purple semi-transparent toast: "Please press Start to connect AI before viewing..."
- Auto-dismisses after 2.6s

---

## 5. Typography Spec

| Role | Font | Source |
|---|---|---|
| Global body | `Inter` | Google Fonts CDN |
| Fallback | `SF Pro Display` | System built-in |
| Reserve | `system-ui`, `sans-serif` | Browser default |

**Exception**: The prototype loads Inter from Google Fonts CDN to satisfy design requirements (SF Pro / Helvetica Neue cannot guarantee cross-platform consistency).

---

## 6. Icon Spec

| Category | Rule |
|---|---|
| **Source** | [Lucide](https://lucide.dev/), CDN loaded via `unpkg.com/lucide@latest` |
| **Style** | Monochrome linear SVG, consistent |
| **Sizes** | `w-3 h-3` (small pill) / `w-4 h-4` (standard) / `w-5 h-5` (buttons) |
| **Init** | Call `lucide.createIcons()` after DOM changes |

---

## 7. No-Emoji Alternatives

Emoji renders inconsistently across operating systems and clashes with the design language — therefore **emojis are completely disabled in the UI rendering layer**.

| Scenario | ✅ Alternative |
|---|---|
| Status/success | Green `<span class="status-dot">` + text "Live · Connected" |
| Disconnected/hang up | Gray dot + text "Disconnected" |
| Notification/toast | Plain text toast, no attached icon |
| Business tags | `tag-hot` (pink background, red text), `tag-instock` (green background, green text), `tag-low` (yellow background, orange text) CSS classes |

---

## 8. Animations & Effects

| Animation | Purpose | Duration/Period |
|---|---|---|
| `breathe` | Orb breathing scale | 4.5s (idle) / 1.2s (listening) / 0.7s (speaking) |
| `halo` | Orb halo expand and fade | 3.4s |
| `core-pulse` | Orb core glow pulse | 2s |
| `wv` | Large waveform ripple | 1.1s (idle paused) |
| `cwv` | Compact waveform ripple | 1s |
| `bubble-in` | Chat bubble entrance | 0.35s ease-out |
| `tdot` | Typing indicator bounce | 1.2s (3 dots 0.2s staggered) |
| `fade-in-down` | Compact bar slide-in | 0.35s ease |
| `detail-in` | Detail page fade-in slide-up | 0.4s ease |
| `pulse-dot` | Connection indicator pulse | 1.6s |

---

## 9. Browser Compatibility

Glassmorphism `backdrop-filter` is unavailable in some older browsers. Glass panels in `styles.css` already declare the `-webkit-backdrop-filter` prefix:

```css
.glass {
  backdrop-filter: blur(22px) saturate(140%);
  -webkit-backdrop-filter: blur(22px) saturate(140%);
}
```

Unsupported browsers will fall back to a solid semi-transparent background (`rgba(255,255,255,0.55)`), ignoring the blur effect.

---

## 10. Status Text

| State | Primary text (ai-state) | Secondary text (ai-substate) | Orb/Wave state |
|---|---|---|---|
| Not connected (pre) | "Ready to start conversation" | "Press Start below to begin a real-time voice session" | idle |
| Idle listening | "Listening for you" | "Speak naturally · I will respond in real time" | idle |
| Listening (listening) | "Listening…" | "Capturing your voice" | listening |
| Thinking (thinking) | "Thinking…" | "Processing your request" | listening |
| AI speaking (speaking) | "AI is speaking…" | "Streaming response over TRTC" | speaking |

---

## 11. Checklist (Self-check before submitting UI)

- [ ] All colors use CSS variables (`--primary`, `--accent-grad`, etc.) or Tailwind presets; bare hex forbidden
- [ ] All icons come from Lucide, sizes in 3 / 4 / 5 (Tailwind `w-* h-*`)
- [ ] No emoji characters in any UI text, status, or buttons
- [ ] Glassmorphism elements include `-webkit-backdrop-filter` prefix
- [ ] Fonts only reference Inter + SF Pro + system-ui combination
- [ ] Orb/Wave animation state transitions correct (idle/listening/speaking three states)
- [ ] Responsive: mobile sidebar shrinks to 50vh
- [ ] Call `lucide.createIcons()` after every DOM insertion of new icons

---

## 12. Admin Board (Ticket Agent Board)

> Scope: `scenarios/customer-service/ui/admin-board/` (served at `/static/admin/`).
>
> **Issue 10 — UI unification**: the admin board shares ONE visual language with the
> customer widget above. It is a light, purple-pink glassmorphism theme — NOT the dark
> teal palette that `tokens.css` ships by default.

### 12.1 Theme override mechanism

`tokens.css` is auto-generated from `design_tokens.json` and ships a dark teal palette
(`--color-bg-gradient: #3A4D4A → #1E2B2B`, white text, green accent). The admin board
does **not** edit `tokens.css`; instead `admin/styles.css` begins with a `:root` block
that re-points the same CSS custom properties to the light palette — exactly mirroring
how the customer widget's `styles.css` overrides its own `tokens.css`. Because
`styles.css` loads after `tokens.css`, the override wins.

### 12.2 Palette mapping (admin override → customer widget equivalent)

| Admin token (`--color-*`) | Admin override value | Customer widget equivalent |
|---|---|---|
| `--color-bg-gradient` | Multi-radial light ambient, base `#f7f3ff` | `.bg-ambient` |
| `--color-bg-surface` | `rgba(255,255,255,0.55)` | `--card` |
| `--color-bg-surface-strong` | `rgba(255,255,255,0.82)` | `--card-strong` |
| `--color-bg-border` | `rgba(155,123,247,0.18)` | purple-tinted stroke (visible on light) |
| `--color-brand-accent` | `#9b7bf7` | `--primary` |
| `--color-text-primary` | `#1a1530` | `--foreground` |
| `--color-text-secondary` | `#6b6580` | `--muted` |
| Status colors | `#1f8e57` / `#3b6bcf` / `#c46500` / `#d6476b` | darker, readable on light |

Glass cards (`.content`, `.filter-rail`, `.drawer`) use `backdrop-filter: blur(20px)` +
a purple-tinted shadow `0 12px 40px -16px rgba(120,90,200,0.22)` for depth on the light
background. Accent buttons (`.btn--accent`) use purple background + white text.

### 12.3 Typography & icons

- Font: `Inter` loaded from Google Fonts CDN (added in `admin/index.html <head>`), falling
  back to `SF Pro` / `system-ui` — identical stack to the customer widget.
- Icons: the admin uses self-contained inline SVGs (no CDN dependency) for reliability.
  They follow the same monochrome linear style as Lucide; no emoji anywhere.

### 12.4 Session summary rendering (issue 2)

The detail drawer renders the session summary attached to a ticket. Field names MUST
match the real `summarizer.summarize()` output:

```
topics: [str]      user_intents: [str]     next_actions: [str]     highlights: [str]
engine: "heuristic" | "llm"                model: str | null
```

> ⚠️ Do NOT use `topic/intent/key_points/suggested_actions` — those names are incorrect.
> The real fields are `topics/user_intents/next_actions/highlights` (all arrays).

If a ticket has no embedded summary, the drawer fetches `GET /api/v1/summary/{session_id}`;
a "Generate summary" button calls `POST /api/v1/summary/{session_id}/finalize` (LLM path).

### 12.5 Customer feedback block (issue 6)

When a ticket carries a `feedback` object (posted by the customer's post-call rating card
via `POST /api/v1/handoff/feedback`), the detail drawer renders a `.feedback-block`:
5-star rating (`★`/`☆`), numeric `n/5` score, and the optional written comment. The
feedback is also written onto the ticket (`ticket.extra["feedback"]`) so it appears in
`GET /api/v1/handoff/admin/tickets` without an extra round-trip.
