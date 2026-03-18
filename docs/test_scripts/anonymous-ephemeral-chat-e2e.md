# Test: Anonymous Ephemeral Chat

## Purpose
Verify that anonymous users on public corpuses get multi-turn conversation,
working timeline, context tracking, and context exhaustion handling.

## Prerequisites
- A public corpus exists with at least one document
- User is NOT logged in (anonymous/incognito)

## Steps

1. Navigate to the public corpus page (anonymous)
2. Open the chat interface
3. Send a message: "What is this corpus about?"
4. Verify:
   - Response streams back (not stuck loading)
   - Timeline shows steps (tool calls, thoughts) — NOT "0 steps"
   - Context meter at bottom shows > 0% after response
5. Send a follow-up: "Can you tell me more about the first document?"
6. Verify:
   - Response references the prior conversation (multi-turn works)
   - Context meter has increased
   - Timeline shows steps for this message too
7. Refresh the page
8. Verify: Chat is gone (ephemeral — not persisted)

## Expected Results
- Multi-turn conversation works within session
- Timeline and context tracking are accurate
- Data is lost on refresh (by design)
