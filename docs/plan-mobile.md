# Plan: Jotva for iPhone

Status: planning (agreed with the founder, 2026-09-27). Nothing built yet.

## Purpose

The Mac is where meetings happen. The iPhone is for everything around them: getting ready,
following through, handling email, and catching the moments away from the desk. It is not a
shrunken copy of the Mac app.

Audience: individual users (there is no team plan yet).

## Free vs Pro

**Free (download is free):** read notes, transcripts and action items; search.

**Pro (the same $12/month subscription, bought on the website through Stripe):**
everything below. The iPhone app does not sell Pro itself (no Apple in-app purchase); it
unlocks for anyone whose install is already Pro, like Notion or Granola.

## Features

### Version 1

1. **Recording on the iPhone.** In-person meetings and conversations, transcribed on the
   phone, notes written the same way as on the Mac. iOS does not let apps record phone calls or
   other apps' audio; the phone records the room, the Mac stays the tool for Zoom/Meet/Teams.
2. **Wisely's email Agent.** Notification "3 emails are waiting on you"; read Wisely's draft;
   send with one tap, or snooze until tomorrow.
3. **Morning briefing and next-meeting prep.** 8 AM: today's meetings, what people owe you,
   emails waiting. Ten minutes before a meeting: attendees, what you discussed last time, open
   promises on both sides, recent emails with them.
4. **Who owes what.** Two lists built from action items: *I owe* and *Owed to me*. When a
   promise is overdue, Wisely drafts a polite nudge to send with one tap.
5. **Follow-up email after the meeting.** Wisely drafts the recap (decisions, next steps) to
   the attendees; review and send from the phone.
6. **Notifications.** Notes ready; meeting starting ("record it on your Mac?"); inbox clear.

### Version 2

7. **Listen in the car.** The briefing or today's recap read aloud by Wisely's voice, in the
   app and in CarPlay. A two-minute private podcast of your day.
8. **Voice jots to Wisely.** Hold a button or ask Siri: "Remind me to send Sarah the contract
   Friday." Wisely files it into the right meeting's notes or the task list, and confirms by
   voice.
9. **Remote for the Mac.** From the phone or Apple Watch: start/stop the Mac's recording, and
   flag a moment ("this is important") that shows up highlighted in the notes.
10. **Scan into a meeting.** Photograph a whiteboard, a slide or a business card; attached to
    the meeting with its text read. A business card becomes a contact plus a draft
    "nice to meet you" email.
11. Ask across meetings, home-screen and Lock Screen widgets, Siri shortcuts.

### Later

Android, iPad, and a team plan.

## Wisely's voice

Wisely gets a voice for the briefings, the car, voice-jot confirmations and short moments
("Your inbox is clear. I'm proud of you!", only when sound is on).

- **Character:** warm, calm, gently witty; a smart friend on your side. Not cartoonish, and
  pleasant to listen to for two minutes every morning.
- **Pro:** a custom-designed voice (ElevenLabs is the leading option). Designed once from a
  description, generating a few candidates for the founder to choose from, the same way
  Wisely's look was chosen. Briefing text is sent to the voice provider to be spoken, using its
  no-storage mode; the privacy policy must say so before launch.
- **Free, and anyone who prefers on-device only:** Apple's built-in voices; nothing leaves the
  phone. A setting lets any user choose on-device only.
- **Cost:** about $5–22/month to start, then a few cents per briefing per user. Set a budget
  and estimate before generating, as with Higgsfield.
- Later: the same voice on the Mac and in the website's "Meet Wisely" section.
- **Voices offered (decided 2026-09-27):** one signature voice by default, plus two alternates and
  "On-device only (Apple voice)" in Settings → Wisely's voice. No voice choice during setup.
- **For now, Wisely speaks in the founder's cloned voice** (from a 20–30 s recording, cloned
  locally with OmniVoice, compared against OpenVoice, which is MIT-licensed). Later it becomes an
  alternate ("Wisely, as read by Jotva's founder") when a designed signature voice takes over.
- **Founder clone: take 2** (founder's pick). Generation settings that sound natural: 64 decoding
  steps, 0.4 s silence after the last word, 0.03 s fade (the defaults clip the final word and
  sound robotic). Scripts: vora-jotva-landing/motion/voice/ (private repo).
- **How Wisely signs off.** Evening recap default: "Nice work today." Day-aware variations keep
  it from sounding recorded:
  - Friday: "Nice work this week. Have a great weekend."
  - Inbox cleared: "Inbox clear, too. Nice work today."
  - Heavy day (5+ meetings): "Long day. Nice work, get some rest."
  Keep sign-offs short; people hear them every day.
- **Talking Wisely (locked in 2026-09-27):** lip sync and blinking are done locally for $0
  (vora-jotva-landing/motion/voice/wisely_talk.py + wisely_blink.py, mouth layers in
  motion/avatar/mouths). Full body in frame, never zoomed to the face. Reference clip:
  motion/voice/videos/wisely-intro-talk.mp4.
- **Knitted Wisely and voice K (decided 2026-09-27):** Wisely's look is now the hand-knitted
  lavender yarn toy (vora-jotva-landing/motion/avatar/materials/wisely-knit.jpg). Feedback said
  the founder's voice doesn't fit him, so his voice is **K**: a soft, higher kid's voice designed
  with OmniVoice (`child, high pitch, american accent`, seed 425; motion/voice/wisely_soft_voices.py,
  with "Jotva" pinned as JOT-vuh). The founder's cloned voice stays a Settings alternate.
- **Knitted Wisely animation:** replacement knitted mouths and stitched blinks
  (motion/voice/knit_talk.py) on a puffy 2.5D body in Blender (motion/blender/knit_wisely.py).
  Video AI (Kling) re-invents his face, so it isn't used for him.
- Engines: OmniVoice (code Apache-2.0; its audio tokenizer is under the Boson Higgs Audio 2
  Community License) and OpenVoice V2 (MIT). VoiceStudio is AGPL-3.0: use it only as a tool,
  never ship its code. Confirm licenses before shipping a voice inside Jotva.

## Sync and storage

Promise to keep: **we never store your meetings or email.**

- The user picks where Jotva keeps its sync folder: **iCloud Drive and Google Drive at
  launch**, then OneDrive and Dropbox; Box when business users ask.
- Jotva on the Mac and iPhone both read and write that folder.
- **Everything in it is encrypted on the device before upload**, with a key only the user's
  devices hold. The storage provider (Apple, Google, Box…) cannot read the meetings.
- **Pairing:** the first time, the iPhone scans a QR code shown on the Mac. That hands over the
  encryption key and the chosen storage securely.
- Not tied to Apple, so the same design serves Android and Windows later.
- Google Drive needs a Drive permission that goes through the same Google verification as
  Gmail (already in progress), not a separate process.
- The older local-network mobile API (`MOBILE_API.md`) only works on the same network with the
  Mac awake; it is superseded by this design.

## How it's built

- **Native iPhone app in Swift/SwiftUI**, for Live Activities (recording timer on the Lock
  Screen), widgets, Apple Watch, Siri/Shortcuts, CarPlay and Apple's on-device speech
  recognition.
- AI notes, briefings and drafts go through the same license-server AI proxy as the Mac.
- Wisely animates on the phone with the existing clips (hello, idle, dance, proud, sad).
- Pro is checked with the same signed license as the Mac.

## Build order (proposal)

1. Sync layer on the Mac: encrypted sync folder, iCloud Drive + Google Drive, QR pairing.
2. iPhone app shell: pairing, reading notes/transcripts/actions, search (the free tier).
3. Pro unlock on the phone.
4. Version 1 Pro features: recording, Wisely's email Agent, briefing and prep, who owes what,
   follow-up email, notifications.
5. Wisely's voice (design and choose), then version 2 starting with Listen in the car.

## Open questions

- Apple Developer account already exists (used for Mac signing); App Store listing, review and
  TestFlight still to set up.
- Where the phone reads email from: synced from the Mac, or its own Google sign-in.
- Voice provider choice and budget.
