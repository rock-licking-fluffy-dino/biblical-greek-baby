# Oikos

Koine Greek study app built around Merkle & Plummer's *Beginning with New Testament Greek* (23 chapters, 345 words). Personal use, shared with classmates. Slogan: "Learning to belong in God's Word."

## How to work on this repo

- Never commit to `main`. Vercel deploys `main` straight to classmates.
- One small task per branch. If a task grows, stop and ask.
- Open a pull request for every change. The owner reviews and merges.
- Make targeted edits. Never rewrite or re-save the whole of `index.html`.
- Do not reformat, re-indent or tidy code outside the task.
- If a change would remove more than 300 lines, stop and ask first.
- State the lines added and removed in every pull request description.
- Say what you tested and what you could not. You cannot test on an iPhone.
- Do not touch `data/`, `manifest.json` or the icons unless the task names them.
- Do not add dependencies or a build step.

## Architecture

- `index.html` is a single self-contained file (about 7,300 lines). Vocabulary is embedded as JSON. No framework, no build step.
- `ts-fsrs` (FSRS-6) loads from a CDN as an ES module. Treat that CDN as a single point of failure for Daily Review.
- PWA for iPhone home-screen install: `manifest.json`, `icon.png`, `icon-180.png`.
- `data/BNTG_Parsing_Practice.xlsx` is the source for the Parse drill. `scripts/build_parse_data.py` builds from it and downloads OpenGNT from a pinned commit.
- Deployed to oikos-eosin.vercel.app. Each branch gets a Vercel preview URL.

## Design rules

- Reuse the tokens in `:root`. Do not invent new colours, radii or spacing.
- Sage green is the brand colour. Light and dark modes must both work.
- No red anywhere. Wrong answers use muted grey (`--surface-2`, `--muted`).
- Radii: `--r-card` 14px, `--r-btn` 12px, `--r-sm` 8px.
- Font is Archivo, loaded at 400, 600 and 800 only. Use only those weights in new CSS.
- Reuse existing patterns before building new ones: `.flip` components, `.ghost-btn` with `.start-btn`, `.missed-row`.
- Typing Greek is not an input method (no Greek keyboard on mobile). Use drag, tap or multiple choice.

## Writing rules

- UK English spelling (practise, recognising, colour).
- No em dashes.
- Short, direct sentences in the owner's voice.

## Scope

- Oikos follows the Merkle & Plummer curriculum in course order. It is not a general NT Greek tool.
- Out of scope: NT frequency ordering, Louw-Nida domains, principal-parts practice, a graded reader.
- Features should work for all 23 chapters, not only the current term.
- Grammar stats stay lightweight (attempts and clean runs). Do not build FSRS for grammar.

## Version history and the Home banner

- Every change classmates will notice gets an entry at the top of `UPDATES` in `index.html`: the next id, the date, a short title and bullet points in the owner's voice.
- Before opening the pull request, ask the owner whether the update should show the banner on Home. Add `notify: true` only if they say yes. Never decide this yourself.
- Ids only go up. Never renumber or remove an old entry.
- Changes nobody will notice (refactors, repo housekeeping) need no entry. Say so in the pull request.

## Decisions to flag, not guess

If a task forces a choice between two reasonable designs, stop and ask. Do not pick one silently.

## Task workflow

- Work from a GitHub issue where one exists. Name the branch `claude/<short-task-name>`.
- Put `Closes #<number>` in the pull request description so the issue closes when it is merged.
- Fill in the pull request checklist honestly. Leave a box unticked if it was not done.
- Do not start a second task on the same branch. Suggest a new issue instead.
