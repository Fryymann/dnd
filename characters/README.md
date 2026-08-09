# Character workshop

This is the working area for discovering, designing, and refining player characters and important NPCs. The process is conversation-first: mechanics support the intended fantasy rather than replacing it.

## Directory layout

- `_template/` — copyable starter workspace for one character.
- `active/` — characters currently being explored, built, played, or revised.
- `archive/` — retired concepts and completed design work worth retaining.

Use one lowercase, hyphenated folder per character, for example:

```text
characters/active/ash-and-iron-paladin/
```

## Character development loop

1. **Seed** — Capture the initial image, fantasy, mood, mechanic, story hook, or table role.
2. **Explore** — Ask focused questions about desired play experience, personality, narrative tensions, mechanics, and constraints.
3. **Branch** — Offer a small number of meaningfully different interpretations rather than prematurely choosing one build.
4. **Choose** — Record decisions and the reasons behind them. Keep rejected ideas when they may be useful later.
5. **Build** — Translate the concept into a rules-legal progression, equipment, spells, tactics, and advancement choices.
6. **Pressure-test** — Check whether the build delivers the intended experience at the actual campaign's levels and table rules.
7. **Iterate** — Return to the concept whenever mechanics or campaign events reveal a mismatch.

## Conversation style

When Hermes helps develop a character, the default approach is:

- begin from Ian's stated intent rather than a generic questionnaire;
- ask only the questions that can materially change the concept;
- mix clarification questions with evocative questions that reveal new possibilities;
- explain what each major answer implies;
- distinguish firm decisions, promising possibilities, and unresolved questions;
- present a few distinct routes when there is a meaningful choice;
- preserve the emotional and narrative core while optimizing mechanics;
- label assumptions about rules version, source availability, campaign level, and house rules.

Questions should feel like collaborative exploration, not form completion. It is fine to draft in passes: concept first, mechanics second, polish last.

## Starting a new character

From the repository root:

```bash
cp -R characters/_template characters/active/<character-slug>
```

Then replace the placeholders in the copied files:

- `README.md` — quick identity, current status, and navigation;
- `workshop.md` — intent, questions, alternatives, decisions, and narrative design;
- `build.md` — rules assumptions and level-by-level mechanical plan.

Add extra files only when useful, such as `backstory.md`, `portrait-prompts.md`, `session-notes.md`, or `sources.md`.
