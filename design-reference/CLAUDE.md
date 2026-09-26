# Jotva — project principles

**Core product principle: Jotva does the organizing.**
Everything is auto-generated from the conversation — the meeting **title**, summary,
actions, decisions, topics, questions, timeline, and highlights. Never ask the user to
type a title, tag, label, or manually organize; titles/knowledge appear *after*
processing (the capture flow reveals the meeting name at the Ready phase).
The one input we invite is the **jot pad**: while recording, the user can jot quick
notes, which steer what the AI emphasizes. It's prominent in the recording card but
always optional. Don't market any of this as "zero manual labor".

## Design language (current — see design-reference/redesign/ and src/jotva-theme.css)
- Dark-first, glassy: ink background with soft blue/violet ambient light, frosted glass panels; a matching light theme.
- The logo gradient (blue → violet) is the only accent; no green (that was the old avocado brand).
- Typography: SF Pro (system font) with a restrained scale — few sizes, weights 400/500/600, calm spacing.
- Glossy "glass lens" highlights glide between items in the dock, meeting tabs and meeting list (`src/glassLens.js`).
- Icons: one system — 24 grid, 1.75 stroke, round caps + joins (rounded-flat family).
- The logo = three layered blue→violet gradient sheets fanned from a shared bottom-left tip. Geometry lives in `src/logoGeometry.js`; `node scripts/build_logo.mjs` regenerates the SVGs and `python3 scripts/render_icon.py` the app/tray icons. While recording, the back sheets fan with the voice level.
- Rounded corners and generous whitespace; gloss is reserved for controls and floating surfaces, never content.

## Structure
- `Jotva Meeting.dc.html` — main canvas: 5g capture flow, 5a Overview, 5c Timeline, 5d Transcript, 5e Ask, 5f Home, 5b moments.
- `JotvaChrome.dc.html` — shared sidebar + meeting list (imported by the app screens).
- `CaptureFlow.dc.html` — animated capture → grow → ready prototype.
