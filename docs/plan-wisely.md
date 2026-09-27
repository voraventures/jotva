# Wisely: the Jotva Agent's avatar

Wisely is the glass quill with round glasses ("Jot smarter."), the face of the Jotva
Agent (Pro). Reference: `vora-jotva-landing/motion/avatar/wisely-reference.png`.
The plain quill without glasses is not Wisely.

## Personality
Helpful, calm, a little nerdy. He does the writing so you don't have to. He never nags:
no bouncing for attention, no guilt. His one signature move: he writes a glowing line,
the same stroke you see in his artwork.

## One source, two places
Wisely is built once in Blender and every animation is rendered from that one scene,
so the website and the app always show the same character.

1. **3D model (Higgsfield → Blender).** Remove the face and glasses from the reference
   image (Higgsfield image edit), then convert the clean quill to 3D (Higgsfield
   image-to-3D, Meshy). Face and glasses are rebuilt in Blender as separate parts so
   he can blink and change expression. Materials match the logo: lavender→blue glass,
   silver nib, black glasses, the same studio light and glow.
2. **Rig in Blender.** The feather bends (a simple bone chain); eyes blink; brows,
   mouth and glasses move; the nib draws the glowing line.
3. **Moods** (short loops, rendered with transparency):

| Mood | What he does | Used for |
|---|---|---|
| Idle | Gentle bob, a blink every few seconds | Default |
| Writing | Nib down, draws the glowing line, eyes follow it | Drafting a reply, notes being written |
| Done | Small happy hop, a light strike across him | Draft ready, notes ready |
| All clear | Relaxed, eyes closed, a soft smile | Nothing waiting on you |
| Heads-up | Glasses nudge up, brows raise | An urgent email |
| Hello | Waves his feather tip | Onboarding, the Pro upsell |

## On the website
- **Email section ("Never leave an email hanging")**: Wisely is the host. Three emails
  stack; he picks the urgent one (Heads-up), writes the reply with his glowing line
  (Writing), then Done with a light strike on "Draft ready". This is the section's
  Blender animation, played as you scroll.
- **Introduced by name**: "Meet Wisely, your Jotva Agent." with his tagline.
- **Small cameos** (optional): a Done pop when the "Notes in seconds" card finishes.
- Never in the hero: the glowing notepad stays the main character.
- Delivered as videos on the section's own background (MP4 + WebM), so no transparency
  is needed and Safari plays them.

## In the app (Agent view)
- **Header**: small Wisely next to "Agent" (Idle).
- **Upsell for Free users**: Hello, with "Meet Wisely, your Agent. Pro."
- **Connect email**: Hello.
- **All clear**: All clear mood replaces the plain check mark.
- **Waiting list**: urgent threads show a tiny Heads-up Wisely instead of the red dot.
- **Drafting**: Writing while a reply is drafted; Done when it's ready, with the line
  "Wisely drafted this in your style".
- Delivered as small transparent WebM loops (Electron/Chromium plays VP9 with alpha),
  with a still PNG fallback and a reduced-motion setting that shows stills only.
- Copy in all six languages (en, es, fr, pt, ko, zh); the name stays "Wisely".

## Order of work
1. Top up Higgsfield (0 credits now); check exact costs before spending.
2. Clean reference image → 3D model → approve a still render of 3D Wisely.
3. Rig + the six moods → approve clips.
4. Website email section with Wisely → private preview.
5. App Agent view with Wisely → ships in the next app update.
