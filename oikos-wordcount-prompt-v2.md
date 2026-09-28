# Oikos: update the "How many words?" options (v2)

Work in the existing single-file app (`index.html`). This is a small, scoped change. Do not touch anything outside it.

## What to change

The "How many words?" step currently offers 10, 20 or 30. Replace those with four options, tied to the course (one chapter = 15 words):

| Option | Label | Sub-label |
|--------|-------|-----------|
| 7 | 7 words | Half a chapter |
| 15 | 15 words | A full chapter |
| 30 | 30 words | Two chapters |
| All | All N words (N = live size of the current selection) | Everything you've picked |

Keep the sub-labels short and in UK English. No em dashes.

## Step 1: find every place this appears

The page appears across the app, so before editing, search the whole file for the hardcoded values (10, 20, 30), for any array or constant that defines them, and for any copy that mentions them (onboarding screens, helper text, empty states). List every location you find and tell me before changing anything if any mode uses the count in a different way. Expected: Multiple Choice, Type Answer and Flashcards. Do NOT change Memory Game (fixed at 10 words / 5 pairs) or Daily Review (daily new-card cap of 10), unless you find they actually use this page.

Define the options once, in a single constant, and have every mode read from it. Do not leave separate copies per mode.

## Step 2: handle small selections and the "All" button

The student picks chapters or categories first, so the pool of available words can be smaller than a fixed option. For example, Chapter 6 alone is 15 words, so 30 cannot be met.

Rules:
- Show all four options. Disable any fixed option (7, 15, 30) larger than the selected pool, in the muted style (`--muted` / `--surface-2`). Never use red.
- "All" is always enabled and shows the live pool size, for example "All 45 words". It updates whenever the chapter or category selection changes.
- If the pool size exactly equals 7, 15 or 30, hide the "All" button, because it would duplicate that option.
- If the pool is smaller than 7, show only "All N words".
- "All" uses every word in the pool once, in shuffled order. Never sample with repeats to reach a number.

Flag it if any of these rules conflicts with how the current selection screen works.

## Step 3: saved preference

If the app remembers the last chosen count (localStorage or `state`), a saved 10, 20 or 30 will no longer match. Migrate old values quietly: 10 to 7, 20 to 15, 30 to 30. If there is no saved value, default to 15. If the saved value is now disabled because the pool is smaller, fall back to the largest enabled option.

## Step 4: check nothing downstream breaks

- Progress bars, "X of Y" counters and end-of-session screens should work at 7 and at very large sizes.
- Test "All" with the whole book selected (345 words). Multiple Choice, Type Answer and Flashcards should all start and finish without lag or layout problems.
- The Type Answer summary screen (if built) should still render correctly with hundreds of rows and scroll sensibly.
- If a session history store exists by now, it should record the actual number asked, not the option label.

## Constraints

- Keep the existing design tokens, radii, Archivo font and light/dark mode support. Four options should sit cleanly in the current layout on a narrow iPhone screen (a 2x2 grid is fine if four in a row is cramped).
- UK English, no em dashes, short direct sentences in any copy.
- Save this prompt as `oikos-wordcount-prompt-v2.md` and do not edit other saved prompt files.

## When done

Tell me: every location changed, how you handled small selections and the "All" button, and anything you left alone on purpose.
