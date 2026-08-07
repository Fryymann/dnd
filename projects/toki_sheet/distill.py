#!/usr/bin/env python3
"""Distill a D&D Beyond character export into the compact payload the Toki sheet embeds.

Usage: python3 distill.py [in.json] [out.json]

The raw export is ~730 KB of API scaffolding. This keeps the sheet-facing subset:
identity, computed defences, actions, spells, inventory, features, steeds, and the
homebrew names/notes Ian keeps in characterValues.
"""
import json
import re
import sys
from pathlib import Path

STAT = {1: "str", 2: "dex", 3: "con", 4: "int", 5: "wis", 6: "cha"}
ABBR = ["str", "dex", "con", "int", "wis", "cha"]
LONG = {"str": "strength", "dex": "dexterity", "con": "constitution",
        "int": "intelligence", "wis": "wisdom", "cha": "charisma"}

# characterValues.typeId -> meaning (D&D Beyond's customization slots)
CV_NAME, CV_NOTE = 8, 9

SKILLS = {
    "acrobatics": "dex", "animal-handling": "wis", "arcana": "int", "athletics": "str",
    "deception": "cha", "history": "int", "insight": "wis", "intimidation": "cha",
    "investigation": "int", "medicine": "wis", "nature": "int", "perception": "wis",
    "performance": "cha", "persuasion": "cha", "religion": "int",
    "sleight-of-hand": "dex", "stealth": "dex", "survival": "wis",
}

ACTIVATION = {
    1: "Action", 2: "No Action", 3: "Bonus Action", 4: "Reaction", 5: "Minute",
    6: "Hour", 7: "Special", 8: "Special", 9: "Special", 10: "Special",
}
# 8/9/10 are Legendary/Mythic/Lair upstream. A PC has none of those — the ids show up
# on riders that attach to another action (Precise Strike, Circle Spell options), so
# they read as "Special" on a player sheet.

RESET = {1: "Short Rest", 2: "Long Rest", 3: "Day", 4: "Special"}

# Full-caster slots by caster level, 1..9. Half-casters index this at ceil(level/2).
SLOT_TABLE = [
    [2], [3], [4, 2], [4, 3], [4, 3, 2], [4, 3, 3], [4, 3, 3, 1], [4, 3, 3, 2],
    [4, 3, 3, 3, 1], [4, 3, 3, 3, 2], [4, 3, 3, 3, 2, 1], [4, 3, 3, 3, 2, 1],
    [4, 3, 3, 3, 2, 1, 1], [4, 3, 3, 3, 2, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1],
    [4, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 2, 1, 1, 1, 1], [4, 3, 3, 3, 3, 1, 1, 1, 1],
    [4, 3, 3, 3, 3, 2, 1, 1, 1], [4, 3, 3, 3, 3, 2, 2, 1, 1],
]
# Multiclass spellcaster level contribution per class.
CASTER_SHARE = {"paladin": 2, "ranger": 2, "artificer": 2,
                "fighter": 3, "rogue": 3,  # Eldritch Knight / Arcane Trickster
                "bard": 1, "cleric": 1, "druid": 1, "sorcerer": 1, "wizard": 1}

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"[ \t]*\n[ \t]*")


def text(html, limit=None):
    """D&D Beyond descriptions are HTML blobs. Flatten to paragraphs the sheet can render."""
    if not html:
        return ""
    s = re.sub(r"</(p|div|li|tr|h\d)>", "\n", html, flags=re.I)
    s = re.sub(r"<li[^>]*>", "• ", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = TAG_RE.sub("", s)
    s = (s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&rsquo;", "’")
          .replace("&lsquo;", "‘").replace("&mdash;", "—").replace("&ndash;", "–")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">"))
    s = WS_RE.sub("\n", s).strip()
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s[:limit].rstrip() + "…" if limit and len(s) > limit else s


def mod(score):
    return (score - 10) // 2


class Sheet:
    def __init__(self, raw):
        self.raw = raw
        self.c = raw["character"]
        self.mods = [m for group in self.c["modifiers"].values() for m in (group or [])]
        self.level = sum(k["level"] for k in self.c["classes"])
        self.prof = 2 + (self.level - 1) // 4
        self.cv = self._character_values()
        self.scores = self._scores()

    # ---- modifier helpers -------------------------------------------------

    def by_sub(self, *subtypes, type=None):
        subs = set(subtypes)
        return [m for m in self.mods
                if m.get("subType") in subs and (type is None or m.get("type") == type)]

    # NOTE ON `isGranted`: it does NOT mean "this modifier applies". It distinguishes
    # automatically-granted entries (class saves, armor, weapon proficiencies) from
    # ones the player CHOSE (skill picks, ability score increases, languages). Both
    # are in effect. Filtering on it drops every ASI and every skill proficiency.
    # Confirmed against D&D Beyond twice: HP 206 / initiative +9 need the ASIs, and
    # passive Perception 22 needs the chosen Perception proficiency plus expertise.

    def bonus(self, *subtypes):
        """Sum fixed/value bonuses for these subtypes."""
        total = 0
        for m in self.by_sub(*subtypes, type="bonus"):
            v = m.get("fixedValue")
            if v is None:
                v = m.get("value")
            if isinstance(v, int):
                total += v
        return total

    def has(self, subtype, type="proficiency"):
        return bool(self.by_sub(subtype, type=type))

    def sense(self, subtype):
        """Largest value granted for a sense (darkvision, blindsight, truesight)."""
        vals = [m.get("fixedValue") or m.get("value") or 0
                for m in self.mods
                if m.get("subType") == subtype and m.get("type") in ("sense", "set-base", "set")]
        return max(vals) if vals else 0

    # ---- pieces -----------------------------------------------------------

    def _character_values(self):
        """Ian renames and annotates things (Crownguard, Save-a-Homie!). Keep both."""
        out = {}
        for v in self.c["characterValues"]:
            if v["typeId"] in (CV_NAME, CV_NOTE) and v.get("value"):
                key = "name" if v["typeId"] == CV_NAME else "note"
                out.setdefault(str(v["valueId"]), {})[key] = v["value"]
        return out

    def _scores(self):
        base = {STAT[s["id"]]: s["value"] or 10 for s in self.c["stats"]}
        for s in self.c["bonusStats"]:
            if s.get("value"):
                base[STAT[s["id"]]] += s["value"]
        for s in self.c["overrideStats"]:
            if s.get("value"):
                base[STAT[s["id"]]] = s["value"]
        for a in ABBR:
            base[a] += self.bonus(f"{LONG[a]}-score")
        return base

    def abilities(self):
        return [{"key": a, "name": LONG[a].title(), "score": self.scores[a],
                 "mod": mod(self.scores[a])} for a in ABBR]

    def saves(self):
        # Aura of Protection: add CHA mod (min +1) to every save while conscious.
        aura = any("aura of protection" in (f["definition"]["name"] or "").lower()
                   for k in self.c["classes"] for f in k.get("classFeatures", []))
        aura_val = max(1, mod(self.scores["cha"])) if aura else 0
        out = []
        for a in ABBR:
            proficient = self.has(f"{LONG[a]}-saving-throws")
            extra = self.bonus(f"{LONG[a]}-saving-throws", "saving-throws")
            out.append({
                "key": a, "name": LONG[a].title(), "proficient": proficient,
                "value": mod(self.scores[a]) + (self.prof if proficient else 0) + extra + aura_val,
                "aura": aura_val,
            })
        return out

    def skills(self):
        out = []
        for slug, ability in sorted(SKILLS.items()):
            proficient = self.has(slug)
            expert = self.has(slug, type="expertise")
            half = self.has(slug, type="half-proficiency")
            rank = 2 if expert else 1 if proficient else 0.5 if half else 0
            out.append({
                "key": slug,
                "name": slug.replace("-", " ").title().replace("Of", "of"),
                "ability": ability, "proficient": proficient, "expertise": expert,
                "value": mod(self.scores[ability]) + int(self.prof * rank) + self.bonus(slug),
            })
        return out

    def defences(self):
        equipped = [i for i in self.c["inventory"] if i.get("equipped")]
        armor = next((i for i in equipped if i["definition"].get("filterType") == "Armor"
                      and i["definition"].get("armorTypeId") in (1, 2, 3)), None)
        shields = [i for i in equipped if i["definition"].get("armorTypeId") == 4]

        dex = mod(self.scores["dex"])
        if armor:
            d = armor["definition"]
            base = d.get("armorClass") or 10
            cap = {1: dex, 2: min(dex, 2), 3: 0}[d["armorTypeId"]]
            magic = sum(m.get("fixedValue") or 0 for m in (d.get("grantedModifiers") or [])
                        if m.get("subType") == "armor-class")
            ac, source = base + cap + magic, d["name"]
        else:
            ac, source = 10 + dex, "Unarmored"

        for s in shields:
            d = s["definition"]
            ac += (d.get("armorClass") or 0) + sum(
                m.get("fixedValue") or 0 for m in (d.get("grantedModifiers") or [])
                if m.get("subType") == "armor-class")
            source += f" + {d['name']}"

        # Worn/attuned wondrous items that grant flat AC (Cloak of Protection, etc.)
        for i in equipped:
            d = i["definition"]
            if d.get("filterType") == "Armor":
                continue
            if d.get("canAttune") and not i.get("isAttuned"):
                continue
            for m in (d.get("grantedModifiers") or []):
                if m.get("subType") == "armor-class" and m.get("fixedValue"):
                    ac += m["fixedValue"]
                    source += f" + {d['name']}"

        con = mod(self.scores["con"])
        hp_max = (self.c["baseHitPoints"] + con * self.level
                  + self.bonus("hit-points-per-level") * self.level)
        if self.c.get("overrideHitPoints"):
            hp_max = self.c["overrideHitPoints"]
        hp_max += self.c.get("bonusHitPoints") or 0

        speed = self.c["race"]["weightSpeeds"]["normal"]["walk"] + self.bonus("speed", "innate-speed-walking")

        return {
            "ac": ac, "acSource": source,
            "hpMax": hp_max,
            "hpRemoved": self.c["removedHitPoints"], "hpTemp": self.c["temporaryHitPoints"],
            "speed": speed,
            "initiative": dex + self.bonus("initiative"),
            "profBonus": self.prof,
            "passivePerception": 10 + next(s["value"] for s in self.skills() if s["key"] == "perception"),
            "passiveInvestigation": 10 + next(s["value"] for s in self.skills() if s["key"] == "investigation"),
            "passiveInsight": 10 + next(s["value"] for s in self.skills() if s["key"] == "insight"),
            "hitDice": [{"die": k["definition"]["hitDice"], "total": k["level"],
                         "used": k.get("hitDiceUsed", 0)} for k in self.c["classes"]],
            "deathSaves": self.c["deathSaves"],
            "senses": [f"{name} {v} ft."
                       for name, v in (("Darkvision", self.sense("darkvision")),
                                       ("Blindsight", self.sense("blindsight")),
                                       ("Truesight", self.sense("truesight")))
                       if v] + [text(s) for s in self.c.get("customSenses", [])],
            "climbSpeed": self.c["race"]["weightSpeeds"]["normal"]["walk"]
                          if self.has("innate-speed-climbing", type="set") else 0,
            "conditions": [c.get("name") for c in self.c.get("conditions", [])],
        }

    def limited_use(self, lu):
        if not lu:
            return None
        maximum = lu.get("maxUses")
        if lu.get("useProficiencyBonus"):
            maximum = (maximum or 0) + self.prof
        return {"max": maximum, "used": lu.get("numberUsed", 0),
                "reset": RESET.get(lu.get("resetType"), "Special"),
                "name": lu.get("name")}

    def slots(self):
        """Resolve spell-slot maxima.

        D&D Beyond's API leaves `spellSlots[].available` at 0 for characters whose
        sheet has never persisted an override — its own web app computes the maxima
        client-side. The authoritative table ships in the very same payload, at
        `classes[].definition.spellRules.levelSpellSlots`, indexed by class level
        (index 0 unused). Read that rather than hardcoding a table here, so any
        class, subclass, or homebrew progression comes out right.
        """
        recorded = [{"level": s["level"], "max": s["available"], "used": s["used"]}
                    for s in self.c["spellSlots"] if s["available"]]
        if recorded:
            return recorded

        casters = [k for k in self.c["classes"]
                   if (k["definition"].get("spellRules") or {}).get("levelSpellSlots")]
        if not casters:
            return []

        if len(casters) == 1:
            k = casters[0]
            table = k["definition"]["spellRules"]["levelSpellSlots"]
            row = table[min(k["level"], len(table) - 1)]
            source = "class table"
        else:
            # Multiclass: pool caster levels by each class's own divisor, then read
            # the shared full-caster progression.
            caster = 0
            for k in casters:
                div = k["definition"]["spellRules"].get("multiClassSpellSlotDivisor") or 1
                caster += k["level"] // div
            if not caster:
                return []
            row = SLOT_TABLE[min(caster, 20) - 1] + [0] * 9
            source = "multiclass table"

        used = {s["level"]: s["used"] for s in self.c["spellSlots"]}
        return [{"level": i + 1, "max": n, "used": used.get(i + 1, 0),
                 "derived": source}
                for i, n in enumerate(row) if n]

    def prepared_max(self):
        """How many spells the character may have prepared, from the class table."""
        total = 0
        for k in self.c["classes"]:
            table = (k["definition"].get("spellRules") or {}).get("levelSpellKnownMaxes") or []
            if table:
                total += table[min(k["level"], len(table) - 1)]
        return total

    def actions(self):
        out = []
        for source, group in self.c["actions"].items():
            for a in (group or []):
                custom = self.cv.get(str(a.get("id")), {})
                out.append({
                    "id": str(a["id"]), "source": source,
                    "name": custom.get("name") or a["name"],
                    "originalName": a["name"] if custom.get("name") else None,
                    "note": custom.get("note"),
                    "activation": ACTIVATION.get((a.get("activation") or {}).get("activationType"), "—"),
                    "range": (a.get("range") or {}).get("range"),
                    "aoe": (a.get("range") or {}).get("aoeSize"),
                    "aoeType": (a.get("range") or {}).get("aoeType"),
                    "dice": (a.get("dice") or {}).get("diceString"),
                    "snippet": text(a.get("snippet")),
                    "description": text(a.get("description")),
                    "limitedUse": self.limited_use(a.get("limitedUse")),
                    "attack": bool(a.get("displayAsAttack")),
                })
        for a in self.c.get("customActions", []):
            if a.get("name", "").startswith("Custom Action"):
                continue  # empty D&D Beyond placeholder rows
            out.append({
                "id": f"custom-{a.get('id')}", "source": "custom", "name": a.get("name"),
                "activation": ACTIVATION.get((a.get("activation") or {}).get("activationType"), "—"),
                "description": text(a.get("description")), "snippet": text(a.get("snippet")),
                "dice": (a.get("dice") or {}).get("diceString"),
                "limitedUse": self.limited_use(a.get("limitedUse")), "attack": bool(a.get("displayAsAttack")),
            })
        return out

    def spells(self):
        seen, out = set(), []
        buckets = list(self.c["spells"].items()) + \
                  [("class-prepared", [s for cs in self.c["classSpells"] for s in cs["spells"]])]
        for source, group in buckets:
            for s in (group or []):
                d = s["definition"]
                key = (d["name"], s.get("castAtLevel"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "name": d["name"], "level": d["level"], "school": d.get("school"),
                    "source": source,
                    "prepared": bool(s.get("prepared")) or bool(s.get("alwaysPrepared")),
                    "alwaysPrepared": bool(s.get("alwaysPrepared")),
                    "ritual": bool(d.get("ritual")), "concentration": bool(d.get("concentration")),
                    "castingTime": text(d.get("castingTimeDescription")) or
                                   ACTIVATION.get((d.get("activation") or {}).get("activationType"), ""),
                    "range": (d.get("range") or {}).get("rangeValue") or (d.get("range") or {}).get("origin"),
                    "duration": (d.get("duration") or {}).get("durationInterval"),
                    "durationUnit": (d.get("duration") or {}).get("durationUnit"),
                    "components": d.get("componentsDescription"),
                    "componentIds": d.get("components"),
                    "snippet": text(d.get("snippet")),
                    "description": text(d.get("description")),
                    "atHigherLevels": text((d.get("atHigherLevels") or {}).get("higherLevelDefinitions") and
                                           " ".join(x.get("details", "") for x in d["atHigherLevels"]["higherLevelDefinitions"])),
                    "usesSlot": s.get("usesSpellSlot", True),
                    "canPrepare": source == "class-prepared"
                                  and bool(s.get("usesSpellSlot", True))
                                  and not s.get("alwaysPrepared"),
                    "limitedUse": self.limited_use(s.get("limitedUse")),
                })
        out.sort(key=lambda s: (s["level"], s["name"]))
        return out

    def inventory(self):
        out = []
        for i in self.c["inventory"]:
            d = i["definition"]
            custom = self.cv.get(str(i.get("id")), {})
            out.append({
                "id": str(i["id"]),
                "name": custom.get("name") or d["name"],
                "originalName": d["name"] if custom.get("name") else None,
                "note": custom.get("note"),
                "type": d.get("filterType"), "subType": d.get("subType"),
                "rarity": d.get("rarity"), "magic": bool(d.get("magic")),
                "quantity": i.get("quantity", 1), "weight": d.get("weight"),
                "equipped": bool(i.get("equipped")), "attuned": bool(i.get("isAttuned")),
                "canAttune": bool(d.get("canAttune")),
                "armorClass": d.get("armorClass"),
                "damage": (d.get("damage") or {}).get("diceString"),
                "damageType": d.get("damageType"),
                "range": d.get("range"), "longRange": d.get("longRange"),
                "properties": [p["name"] for p in (d.get("properties") or [])],
                # The Dragonlance's +3 and its 3d6-vs-dragons rider live here, not in
                # the name — inferring "+1" from the title misses both.
                "magicBonus": sum(m.get("fixedValue") or 0
                                  for m in (d.get("grantedModifiers") or [])
                                  if m.get("subType") == "magic"),
                "riders": [{"dice": (m.get("dice") or {}).get("diceString"),
                            "damageType": m.get("subType"),
                            "when": m.get("restriction") or ""}
                           for m in (d.get("grantedModifiers") or [])
                           if m.get("type") == "damage" and (m.get("dice") or {}).get("diceString")],
                "snippet": text(d.get("snippet")),
                "description": text(d.get("description"), 4000),
                "limitedUse": self.limited_use(i.get("limitedUse")),
                "chargesUsed": i.get("chargesUsed", 0),
            })
        for ci in self.c.get("customItems", []):
            out.append({"id": f"custom-{ci.get('id')}", "name": ci.get("name"), "custom": True,
                        "quantity": ci.get("quantity", 1), "weight": ci.get("weight"),
                        "description": text(ci.get("description"))})
        return out

    def features(self):
        out = []
        for k in self.c["classes"]:
            for f in k.get("classFeatures", []):
                d = f["definition"]
                if d.get("hideInSheet") or d.get("requiredLevel", 0) > k["level"]:
                    continue
                out.append({
                    "name": d["name"], "level": d.get("requiredLevel"),
                    "source": (k.get("subclassDefinition") or {}).get("name") if d.get("isSubClassFeature")
                              else k["definition"]["name"],
                    "subclass": bool(d.get("isSubClassFeature")),
                    "snippet": text(d.get("snippet")),
                    "description": text(d.get("description"), 6000),
                    "levelScale": (f.get("levelScale") or {}).get("description"),
                })
        out.sort(key=lambda f: (f["level"] or 0, f["name"]))
        return out

    def feats(self):
        return [{
            "name": f["definition"]["name"],
            "snippet": text(f["definition"].get("snippet")),
            "description": text(f["definition"].get("description"), 4000),
        } for f in self.c["feats"]]

    def steeds(self):
        out = []
        for cr in self.c.get("creatures", []):
            d = cr["definition"]
            out.append({
                "name": cr.get("name") or d["name"], "base": d["name"],
                "active": bool(cr.get("isActive")),
                "ac": d.get("armorClass"), "acDesc": d.get("armorClassDescription"),
                "hpMax": d.get("averageHitPoints"), "hpRemoved": cr.get("removedHitPoints", 0),
                "hpTemp": cr.get("temporaryHitPoints", 0), "hitDice": d.get("hitPointDice"),
                "speeds": [f"{m['speed']} ft. {m['movementId']}" for m in (d.get("movements") or [])],
                "movements": d.get("movements"),
                "senses": d.get("senses"), "passivePerception": d.get("passivePerception"),
                "skills": d.get("skills"), "savingThrows": d.get("savingThrows"),
                "actions": text(d.get("actionsDescription")),
                "reactions": text(d.get("reactionsDescription")),
                "traits": text(d.get("characteristicsDescription")),
                "note": text(cr.get("description")),
                "avatar": d.get("avatarUrl"),
            })
        return out

    def identity(self):
        c = self.c
        return {
            "name": c["name"], "id": c["id"], "url": c.get("readonlyUrl"),
            "level": self.level,
            "classes": [{"name": k["definition"]["name"], "level": k["level"],
                         "subclass": (k.get("subclassDefinition") or {}).get("name"),
                         "hitDie": k["definition"]["hitDice"]} for k in c["classes"]],
            "race": c["race"].get("fullName") or c["race"].get("baseName"),
            "background": ((c.get("background") or {}).get("definition") or {}).get("name"),
            "backgroundDescription": text((((c.get("background") or {}).get("definition")) or {}).get("description"), 3000),
            "xp": c.get("currentXp"), "inspiration": bool(c.get("inspiration")),
            "age": c.get("age"), "height": c.get("height"), "weight": c.get("weight"),
            "hair": c.get("hair"), "eyes": c.get("eyes"), "skin": c.get("skin"),
            "gender": c.get("gender"), "faith": c.get("faith"),
            "avatar": (c.get("decorations") or {}).get("avatarUrl"),
            "currencies": c.get("currencies"),
        }

    def story(self):
        t = self.c.get("traits") or {}
        n = self.c.get("notes") or {}
        return {
            "appearance": t.get("appearance") or "",
            "personality": t.get("personalityTraits") or "",
            "ideals": t.get("ideals") or "",
            "bonds": t.get("bonds") or "",
            "flaws": t.get("flaws") or "",
            "backstory": text(n.get("backstory")),
            "allies": text(n.get("allies")), "enemies": text(n.get("enemies")),
            "organizations": text(n.get("organizations")),
            "possessions": text(n.get("personalPossessions")),
            "holdings": text(n.get("otherHoldings")), "other": text(n.get("otherNotes")),
        }

    def build(self):
        return {
            "exportedAt": self.raw.get("exportedAt"),
            "source": self.raw.get("source"),
            "identity": self.identity(),
            "abilities": self.abilities(),
            "saves": self.saves(),
            "skills": self.skills(),
            "defences": self.defences(),
            "spellcasting": {
                "slots": self.slots(),
                "preparedMax": self.prepared_max(),
                "dc": 8 + self.prof + mod(self.scores["cha"]),
                "attack": self.prof + mod(self.scores["cha"]),
                "ability": "Charisma",
            },
            "actions": self.actions(),
            "spells": self.spells(),
            "inventory": self.inventory(),
            "features": self.features(),
            "feats": self.feats(),
            "steeds": self.steeds(),
            "story": self.story(),
        }


def main():
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else "character_exports/dndbeyond-toki-ironlung.json")
    dst = Path(sys.argv[2] if len(sys.argv) > 2
               else "projects/toki_sheet/toki.data.json")
    sheet = Sheet(json.loads(src.read_text()))
    data = sheet.build()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))

    d = data["defences"]
    print(f"{src.stat().st_size/1024:.0f} KB -> {dst.stat().st_size/1024:.0f} KB  {dst}")
    print(f"  {data['identity']['name']}  {data['identity']['race']} "
          f"{'/'.join(f'{c['name']} {c['level']}' for c in data['identity']['classes'])}")
    print(f"  AC {d['ac']} ({d['acSource']})  HP {d['hpMax']}  Init {d['initiative']:+d}  "
          f"Speed {d['speed']}  Prof +{d['profBonus']}")
    print("  saves " + "  ".join(f"{s['key'].upper()} {s['value']:+d}" for s in data["saves"]))
    print(f"  spell DC {data['spellcasting']['dc']}  atk {data['spellcasting']['attack']:+d}  "
          f"slots {[(s['level'], s['max']) for s in data['spellcasting']['slots']]}")
    print(f"  {len(data['actions'])} actions  {len(data['spells'])} spells  "
          f"{len(data['inventory'])} items  {len(data['features'])} features  "
          f"{len(data['feats'])} feats  {len(data['steeds'])} steeds")


if __name__ == "__main__":
    main()
