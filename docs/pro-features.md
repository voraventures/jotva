# Jotva plans — what to advertise

The source of truth for the website's pricing and feature pages. **Keep this
updated whenever a feature moves between plans or a new Pro feature ships.** The
feature keys match `PRO_FEATURES` in `backend/app/services/license.py`.

## Pricing

| Plan | Price |
|---|---|
| **Free** | $0, forever |
| **Pro** | **$12 / month** (Stripe product "Jotva Pro") |

Positioning: recording and transcription are free with no limits, because they
run on the user's Mac. For comparison, Granola Business is $14/month.

## Free, forever

- **Unlimited recording and transcription.** Runs on the user's Mac, so it's private and free.
- **AI notes for 10 meetings a month:** summary, key discussions, decisions and action items with owners and real due dates.
- **Jot pad.** Type quick notes while recording, and the AI makes sure every jot is covered.
- **Notes that write themselves in seconds after Stop**, filling in live on the meeting page.
- **Your meetings, always yours.** Search, transcripts, audio and all past notes stay readable and exportable. Nothing is ever locked away.
- **Calendar reminders.** Jotva asks to record when a calendar meeting starts, and calendar meetings are named automatically.
- **Bring your own AI key** (Anthropic, OpenAI or Google) for unlimited notes with any model.

## Pro — $12/month

| Feature | Pitch | Where it lives in the app | Key |
|---|---|---|---|
| **Unlimited AI notes** | No monthly cap on meeting notes. | Everywhere; free users see a meter in Settings → Subscription | `unlimited_notes` |
| **Live notes** | Key points, decisions and action items build up while you talk, not just after. | Recording window → "Live notes" tab; on/off in Settings → Recording | `live_notes` |
| **Ask across all your meetings** | "What did we decide about pricing?" Answers from every meeting at once. | Search → Ask | `ask_all` |
| **Automatic calendar recording** | Jotva starts recording your calendar meetings on its own, so you never miss one. | Settings → Recording / Calendars → auto mode | `auto_record` |
| **Higher-quality AI notes** | Our most capable AI for deeper, more precise notes. | Settings → AI → Quality | `higher_quality` |
| **Follow-up emails** | A ready-to-send follow-up email from any meeting, in one click. | Meeting → ⋯ → Follow-up | `followup` |
| **Custom templates** | Notes shaped exactly how you like them. | Settings → Templates → New template | `templates` |
| **Share to Slack, Notion and your team** | Send notes where your team already works. | Meeting → Send to / Share with team | `integrations` |
| **Access from Claude and other AI assistants** | Let Claude, Cursor and other assistants read your meeting notes (MCP), with your permission. | Settings → Integrations → AI assistants | `mcp` |

## Messaging notes

- Lead with privacy and speed: on-device transcription, notes seconds after the meeting.
- Don't advertise "zero manual labor". The jot pad is the one input we invite, and it's optional.
- Name: just "Jotva". Domain: getjotva.com (to be purchased).
