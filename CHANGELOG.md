# Changelog

All notable changes to Vivarium are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [Unreleased]

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
