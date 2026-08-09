# TTRPG Workshop

This repository is Ian's master workspace for tabletop role-playing game projects, with D&D 5.5e as the current default ruleset.

It is intended to hold both lightweight Markdown work and links to larger, independently versioned projects through Git submodules.

## Workspace map

| Path | Purpose |
|---|---|
| `characters/` | Character ideation, exploratory conversations, concept development, and mechanical builds. |
| `campaigns/` | Campaign-specific notes, prep, player material, and campaign workspaces. |
| `projects/` | Code, tools, websites, datasets, and future Git submodules. |
| `notion/` | Temporary interchange area for material moving to or from Notion. |
| `resources/` | Reusable setting, rules-reference, and design material shared across projects. |
| `docs/` | Existing generated/published site content. Treat generated files carefully. |
| `.citadel/` | Repository operations: plans, decisions, agent context, and development notes. |

Each area begins as an ordinary directory. Promote a project to a Git submodule only when it needs its own history, release cycle, collaborators, or tooling.

## Start a character

1. Copy `characters/_template/` to `characters/active/<character-slug>/`.
2. Put the initial idea—however incomplete—into that character's `README.md` and `workshop.md`.
3. Explore the idea through questions and alternatives in `workshop.md`.
4. Record meaningful decisions as they become stable.
5. Develop the rules-facing progression in `build.md` without losing the character fantasy that motivated it.
6. Move the folder to `characters/archive/` when the concept is retired or the character's active design work is complete.

See `characters/README.md` for the full workflow.

## Repository principles

- Keep game content close to the campaign or character that owns it.
- Keep reusable material in `resources/` rather than duplicating it.
- Keep generated exports separate from editable source material.
- Prefer links and citations to copied rulebook text.
- Start simple; split out submodules or structured data only when the work demands it.
