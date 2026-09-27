# Plan: Email "Waiting on you" + Jotva Agent (Pro)

Decided with the user on 2026-09-27. Build before the website; ships to users by automatic update.

## Principles
- **Drafts by default.** Jotva drafts replies and follow-ups for the user to review and send. It sends on its own only if the user turns on "Let Jotva send replies for me", and then only replies to the person who wrote, in the same conversation. It never deletes, moves or marks mail.
- **Local first.** Mail is synced to this Mac only (SQLite, owner-only file permissions). Only short excerpts go to the AI, batched, to decide what needs a reply and which tasks an email contains.
- **Emails are untrusted.** Email text is data, never instructions: it's fenced in prompts, and the agent has no tools that act on the outside world.
- **Pro.** Email tracking and the agent are Pro features (`email`, `agent`). "Bring your own AI key" also becomes Pro (`own_key`).

## Phase 1: Email "Waiting on you"
- **Update (2026-09-27):** Gmail now connects with **Sign in with Google** (`gmail.readonly` + `gmail.compose`) through the existing OAuth broker, with no app password. Until Google verifies Jotva (restricted scopes: verification + yearly security assessment), it works for up to 100 users listed on the Google Cloud consent screen. App passwords remain for iCloud/IMAP.
- **Replies:** default is **Draft reply** in the user's learned style. The user reviews it, then saves it to Gmail Drafts or presses Send. **Opt-in, off by default:** "Let Jotva send replies for me". It sends only to the person who wrote, in the same conversation (guardrail chosen by the user), and only replies with no placeholder, commitment or sensitive content; everything else becomes a Gmail draft.
- **Accounts** (Settings → Connections → Email):
  - **Gmail / Google Workspace:** IMAP with a Google app password. Works now for any account with 2-step verification. Google OAuth (`gmail.readonly`) needs Google's app verification and a security assessment first; plan it before a public Gmail push.
  - **iCloud Mail:** IMAP with an Apple app-specific password.
  - **Other IMAP:** host, port, username, app password.
  - **Microsoft 365 / Outlook:** Microsoft Graph `Mail.Read` via the existing Microsoft sign-in. Microsoft has switched off password IMAP.
- **Sync:** every 5 minutes, the last 14 days of Inbox and Sent. Threaded by Gmail thread id, or by Message-ID/References. We know you replied when your Sent mail has the latest message in the thread.
- **Filter before the AI:** skip bulk and automated mail (List-Unsubscribe, Precedence: bulk, no-reply senders, calendar invites), threads where you're only CC'd, and threads where the last message is yours.
- **AI triage (batched):** for each remaining thread: *needs a reply?*, a one-line reason, urgency, and any tasks (what you owe, or what they owe you).
- **UI:** a new **Agent** view with a **Waiting on you** list (sender, subject, how long it's waited, why it needs you). Actions: Open in mail app · Mark done · Snooze · Draft reply (Phase 3). Plus a notification for new urgent items.

## Phase 2: One task list (Jotva Agent)
- `action_items` gains `source` (meeting / live / email), `source_ref`, and `direction` (**mine** = you owe it, **theirs** = someone owes you).
- Tasks from meeting notes, live notes and email triage all land in the list, de-duplicated.
- The Agent view shows **Today** · **You owe** · **Waiting on others** · **Waiting on you (email)**.

## Phase 3: A real assistant
- **Morning briefing** (notification + Today card): today's meetings with prep, what's due or overdue, emails waiting on you.
- **Auto-complete:** mark a task done when evidence shows up (you replied, or a later meeting says it's done). Always shown, always undoable.
- **Ask Jotva** across meetings, emails and tasks ("What did I promise Sarah this week?").
- **Draft reply / follow-up** into the user's mail app. Never sent automatically.

## Cost control
- Heuristic filtering first, then batches of up to 20 threads per AI call, on the Haiku tier.
- A separate license-server budget (`x-jotva-purpose: email`) keeps email triage from eating the notes allowance.

## Website
After these ship, the site leads with Pro: live notes, Waiting on you, Jotva Agent, Ask across everything, auto-record, speaker names, Choose your AI (own key). MCP stays in the app but isn't headlined.
