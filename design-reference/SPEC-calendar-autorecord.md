# Calendar-linked auto-recording — plan

## Principle
Extends "Jotva does the organizing": for calendar meetings, the user does nothing at all —
no manual Record tap required. Manual Record remains for ad-hoc/unscheduled conversations.

## Flow
1. **Connect calendar** — Google / Apple / Outlook. Already exists in Settings; not
   redesigned in this pass.
2. Jotva reads upcoming events that carry a video-call link (Zoom/Meet/Teams).
3. **1 minute before start** (shipped as 1 min, originally specced as 5) — an in-app
   banner/toast appears (non-blocking, dismissible) with a **Join** button:
   *"[Meeting title] starts in 1 min — Jotva will auto-transcribe once you join."*
4. **Join detection** — as shipped: clicking Join opens the call link and starts an
   audio-activity watcher (services/presence.py); once sustained talking is heard the
   normal record prompt / auto-start fires. Native Zoom/Meet/Teams join hooks remain
   out of scope.
5. Recording + transcription start automatically. The meeting behaves exactly like a
   manually captured one from here (processing → ready → Overview/Timeline/Transcript/Ask).
6. **Manual "Record"** (sidebar) stays for ad-hoc meetings with no calendar event — same
   capture flow, just user-triggered instead of calendar-triggered.

## New states needed
- **Scheduled/upcoming** meeting card — shown in the Meetings list *before* the event
  starts, so the user can see and trust what Jotva is about to auto-capture.
- **Banner/toast** — the 1-minute heads-up with Join. Transient, dismissible, calm (not a modal).
- (Low priority) a subtle source indicator — calendar-triggered vs manually recorded —
  on the meeting card, if useful later.

## Meetings list changes
Add an **"Upcoming"** group above "Today": each row shows time-until-start, the event
title (from the calendar — may not match the eventual AI-generated meeting name), and a
quiet "will auto-transcribe" affordance so the user isn't surprised when recording starts.

## Explicitly out of scope for this pass
- Redesigning the calendar-connect screen in Settings (exists already).
- Actual Zoom/Meet/Teams SDK/join-detection engineering.

## Design options explored
See canvas, turn 6: three treatments for the upcoming/scheduled list row + the 5-minute
banner/toast.
