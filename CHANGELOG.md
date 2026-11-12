# Changelog

All notable changes to Vivarium are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [Unreleased]

## [0.1.1] - 2026-11-12

### Security
- Imported challenge codes are clamped: `decode_genome` now pushes every gene
  through the same clamp the birth path uses (one shared helper, `clamp_gene`),
  so a hostile code carrying `sense = 10^9` can no longer turn the sense scan
  into a four-quintillion-cell loop on every tool call. Non-finite values
  (NaN, inf) are refused with a `ValueError`; big numbers are clamped, not
  refused. `release_creatures` keeps a backstop clamp for callers that hand it
  raw genomes.
- Profile-safe paths: the skills-dir resolution and the delivery trace now
  derive their Hermes home from the running profile (the bound plugin data
  dir first, then `$HERMES_HOME`, with the default home only as the last
  fallback), so a non-default Hermes profile no longer reads or writes the
  default profile's tree.
- The serve gallery answers 403 unless the Host header is a loopback name on
  the actual serving port (127.0.0.1, localhost or [::1]), closing the
  DNS-rebinding read of `/live/dish.json` from a browser page.

### Fixed
- VIV-104: the serve page's featured "latest birth" card follows the newest
  birth EVENT, not dict insertion order. A re-birth (VIV-61: a skill with an
  older-era registry row births again) re-assigns its existing key in the
  births dict and Python keeps that key's original position, so picking the
  last entry pinned the second-to-last birth forever ("first skill flips,
  second doesn't"). Every birth-record writer (skill birth, older-era
  re-birth, Big Bang seeding) now stamps a monotonic `seq`, and ONE shared
  selector (`birth.newest_birth`) drives both the build-time page and the
  serve's live poll. The live card morph can now CREATE the featured card on
  a page built before the first birth, and guards on seq as well as the
  Eidos hex so same-species re-births morph too. `_face_svg` never ships an
  empty face: unrenderable genomes degrade to a deterministic fallback face
  instead of leaving the previous Hermi's face under a new name.

## [0.1.0] - 2026-11-11

First public release, submitted to the Hermes Agent Plugin Hackathon.

### Added
- The dish: a persistent 48x48 cellular-automaton world. Real agent activity
  drives it - every tool call drops nutrients, a busy day is a population boom,
  a quiet day is a famine, and eras roll over as the agent works.
- Species from skills: every skill the agent learns births a new Hermi species,
  derived deterministically from the skill's content. Names and raw content are
  never stored or published.
- Genome and lineage: 224-bit genomes (forage, sense, metabolism, aggression,
  mutation rate, dispersal, plus the fixed hue), inheritance with mutation,
  natural selection, extinction and descent lines recorded in a registry.
- Slash commands: `/vivarium` to wake the dish, plus `status`, `births`,
  `milestones`, `show`, `clip`, `serve`, `explain` and more.
- Seeding and ancestry: deterministic canon digests seed pods of Hermi; your
  first skills shape which lineages survive.
- Import and export: species travel as signed challenge codes, verified before
  they can enter a dish.
- The private gallery: `/vivarium serve` serves the live dish, the registry and
  every Hermi on 127.0.0.1 only - no CDN, no external fonts, nothing leaves
  the machine.
- Terminal art: the dish, birth cards, milestone stamps and cinematic clips
  rendered on the terminal. The core renders are pure stdlib; clips use an
  optional Pillow install.
- Privacy posture: no network calls, no telemetry, no shell commands; the
  universe key stays in local plugin state (0600).
- 369 tests green, with a dedicated test proving the core renders with every
  third-party import blocked.
