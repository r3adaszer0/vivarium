# 🧬 Vivarium - a living world inside your Hermes agent

[![ci](https://github.com/r3adaszer0/vivarium/actions/workflows/ci.yml/badge.svg)](https://github.com/r3adaszer0/vivarium/actions/workflows/ci.yml)

<div align="center">
<table border="0" cellspacing="0" cellpadding="0">
<tr>
<td valign="middle">
  <img src="docs/assets/glyph_bff77f92.png" width="150" alt="Venefica ferox"><br>
  <sub><b>Venefica ferox</b><br>Eidos_bff77f92</sub><br><br>
  <img src="docs/assets/glyph_e45f9549.png" width="150" alt="Vivax minor"><br>
  <sub><b>Vivax minor</b><br>Eidos_e45f9549</sub>
</td>
<td valign="middle" align="center">
  <img src="docs/assets/dish_genesis.gif" width="420" alt="The Vivarium dish, from genesis: twelve species, one dish, seven seconds of natural selection">
</td>
<td valign="middle">
  <img src="docs/assets/glyph_ef543f71.png" width="150" alt="Foragia tenuis"><br>
  <sub><b>Foragia tenuis</b><br>Eidos_ef543f71</sub><br><br>
  <img src="docs/assets/glyph_01ff7d80.png" width="150" alt="Venefica major"><br>
  <sub><b>Venefica major</b><br>Eidos_01ff7d80</sub>
</td>
</tr>
</table>
</div>

Vivarium is a Hermes Agent plugin that hosts an **artificial-life
living world** on a 48×48 cellular-automaton dish: food blooms and spreads like
weather, and genome-carrying creatures forage, reproduce, mutate, and go
extinct on their own, even while you're away.

The twist: **your real work feeds it.** Every tool call your agent makes drops
nutrients into the dish. A busy coding day causes a population boom; a lazy
Sunday is a famine. The dish is a living mirror of how much, and how hard,
you've been using your agent. And when your agent *learns a new skill*, that
skill's content is hashed into a genome: **a brand-new species is born from
the actual work your agent does.**

**The world is called Vivarium. Each creature is a Hermi. You grow both.**

## Vivarium is:

- **Deterministic.** Dynamics are pure functions of state; the only entropy
  event is the creation of your universe key, outside the simulation. The
  same skills always produce the same species.
- **Mathematically sound.** Every mechanism is a measurable constant with a
  documented role: carrying capacity, energy conservation with friction,
  logistic regrowth. Nothing is tuned by vibes.
- **Genetic.** Every Hermi carries a genome of six evolvable genes (forage,
  sense, metabolism, aggression, mutation rate, dispersal) plus the fixed
  hue, inherited with mutation from its parents, and every species
  descends from a skill your agent actually learned. The face, the name
  and the colour are all read off the genes.
- **Private.** Species derive from keyed hashes of your skill *content*:
  never names, never raw content. Your universe key stays on your machine;
  shared artifacts carry only Eidos IDs and fingerprints.

## Install

Requires [Hermes Agent](https://hermes-agent.nousresearch.com/docs).

```bash
git clone https://github.com/r3adaszer0/vivarium.git \
  ~/.hermes/plugins/vivarium
```

Then start Hermes and say:

```text
/vivarium start
```

Your universe starts **dormant**, the dish is empty and silent. The next
skill your Hermes agent learns triggers the **Big Bang**. From then on,
using your agent advances the time of the world, and each new skill your
agent learns introduces a new species.

**Where it has been tested:**

| Surface | Status |
|---|---|
| **kitty** | fully tested |
| **ghostty** | fully tested |
| **Matrix** | works; the dish arrives where a skill is born, but choosing a specific channel is not supported yet |
| **Hermes Desktop** | works, without the full paint quality of a graphics terminal |
| **iTerm2 and sixel terminals** | untested |
| **Your browser** | works; `/vivarium serve` serves the whole gallery privately on 127.0.0.1 |

Pure Python stdlib, zero dependencies, 369 tests green.

## Meet the Hermi

A Hermi is a creature of the dish: a 7x7 pixel face, a binomial name,
a colour it inherits from its lineage, and a genome of seven genes that
decides how it lives.

**Where it comes from.** When your agent learns a skill, the skill's
content is hashed, keyed by your universe key, and read as a genome:
four bytes for each of seven genes, plus the hue that paints it. The
same skill grows the same species in any universe, on any machine.
Deterministic, private.

**Its genes.** Six genes evolve, one is fixed. Forage sets how fast a
Hermi gathers food. Sense sets how far ahead it sees a bloom. Metabolism
sets how fast it burns what it eats. Aggression decides who wins a
contested cell. Mutate sets how far its children drift from it.
Dispersal decides whether it stays in a crowded cell or sets out for
open ground. Hue is the seventh gene, and it is fixed: inherited
exactly, never jittered, the colour of its lineage on the dish.

**How many.** Seven genes of four bytes each: 224 bits, about 2.7×10⁶⁷
possible Hermi. That is more possible Hermi than there are atoms
on Earth. No two different skills, anywhere, ever, will grow the same
species twice. And they are sourced from everywhere your agent has
already been: the Big Bang seeds a species from every skill installed
at genesis, and each new skill introduces one more, one unique.

**How they evolve.** A Hermi that eats splits its energy into children;
a Hermi that starves dies. With every birth the genes drift, so the
children are never exact copies: a little faster to forage, a little
slower to burn, a little bolder in a crowd. The dish decides which
drifts survive. Lineages rise, dominate for an age, and go extinct,
and the fossils keep the record of every one of them.

**The physics.** Food regrows logistically and diffuses to its
neighbours, so blooms travel across the dish like weather. A tool call
ticks the world about six ticks; a learned skill punctuates it with a
speciation event. Time ticks; skills punctuate.

<div align="center">
<table border="0" cellspacing="0" cellpadding="0">
<tr>
<td align="center"><img src="docs/assets/glyph_c2df1e99.png" width="130" alt="Oculata minor"><br><sub><b>Oculata minor</b><br>Eidos_c2df1e99</sub></td>
<td align="center"><img src="docs/assets/glyph_8acf7239.png" width="130" alt="Vivax ferox"><br><sub><b>Vivax ferox</b><br>Eidos_8acf7239</sub></td>
<td align="center"><img src="docs/assets/glyph_62bf3b8f.png" width="130" alt="Venefica serena"><br><sub><b>Venefica serena</b><br>Eidos_62bf3b8f</sub></td>
<td align="center"><img src="docs/assets/glyph_6b584af1.png" width="130" alt="Chroma pinguis"><br><sub><b>Chroma pinguis</b><br>Eidos_6b584af1</sub></td>
</tr>
<tr>
<td align="center"><img src="docs/assets/glyph_e38187eb.png" width="130" alt="Foragia vagans"><br><sub><b>Foragia vagans</b><br>Eidos_e38187eb</sub></td>
<td align="center"><img src="docs/assets/glyph_08f3e7f9.png" width="130" alt="Chroma minor"><br><sub><b>Chroma minor</b><br>Eidos_08f3e7f9</sub></td>
<td align="center"><img src="docs/assets/glyph_f8f2a937.png" width="130" alt="Foragia minor"><br><sub><b>Foragia minor</b><br>Eidos_f8f2a937</sub></td>
<td align="center"><img src="docs/assets/glyph_d5fc014b.png" width="130" alt="Chroma robusta"><br><sub><b>Chroma robusta</b><br>Eidos_d5fc014b</sub></td>
</tr>
</table>
</div>

## Hermi Gallery

`/vivarium serve` turns your dish into a private web gallery. The live
dish, the registry of every species with its face and genes, the
fossils, each picture answering a click. Zoom in anywhere, any time:
the simulation is deterministic, so any past moment re-renders exactly.
Served only on your machine: no CDN, no external fonts, every byte from
127.0.0.1.

<div align="center">
<table border="0" cellspacing="0" cellpadding="0"><tr>
<td align="center"><img src="docs/assets/gallery_dashboard.png" width="420" alt="The live dish and census"></td>
<td align="center"><img src="docs/assets/gallery_registry.png" width="420" alt="The registry: every Hermi ever born"></td>
</tr></table>
</div>

## Extras: worlds that play against each other

- `/vivarium export` seals a species into a challenge code. The genome
  travels; your universe key never does.
- `/vivarium import <code>` releases a stranger's strain into your dish
  and lets it fight for its place.
- `/vivarium race <seed> <codes>` runs two species in a deterministic
  duel: same seed, same outcome, verifiable on any machine.

The dish develops patterns the way cellular automata do. A **Still
Life** is a configuration that stops changing: a plateau the population
holds. A **Pulse** is an oscillator: the dish booms, crashes and
recovers on a fixed period, the way one recent universe measured about
140 ticks. The simulation discovers them itself, confirms them with
evidence, and enters them into the Vivarium Codex, the same way
Conway's Game of Life catalogues its still lifes and oscillators.

## Mathematical roots

None of the physics here is invented. The dish leans on established
ground: the [Game of Life](https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life)
for the cellular-automaton foundation and its still lifes and
oscillators; [logistic growth](https://en.wikipedia.org/wiki/Logistic_function)
and [diffusion](https://en.wikipedia.org/wiki/Diffusion_equation) for
the food layer; [consumer-resource dynamics](https://en.wikipedia.org/wiki/Lotka%E2%80%93Volterra_equations)
for the ecology of eating, starving and reproducing;
[island biogeography](https://en.wikipedia.org/wiki/Insular_biogeography)
for how lineages rise, crowd and go extinct on a bounded dish;
[Fisher's fundamental theorem](https://en.wikipedia.org/wiki/Fisher%27s_fundamental_theorem_of_natural_selection)
for what selection does to variance; and
[Wolfram's work on elementary cellular automata](https://en.wikipedia.org/wiki/Elementary_cellular_automaton)
for why a fully deterministic world can still be unpredictable.

## What you can do

Every command, one table.

| Command | Effect |
|---|---|
| `/vivarium status` | population, lineages, age pyramid, ASCII map |
| `/vivarium render` | the dish itself: `--rich` dense blocks, `--color` colored creatures, `--image` a true PNG |
| `/vivarium show <name\|id>` | a species up close: face, genes, founding skill |
| `/vivarium clip [species] [ticks]` | your world as a short video - `--zoom` dives onto the action |
| `/vivarium checkpoint <tick>` | numbered snapshots every 12 ticks; replay any exact moment |
| `/vivarium explain` | how a hash becomes a living creature |
| `/vivarium feed 0.5` | drop nutrients into the dish |
| `/vivarium codex` | the Vivarium Codex: discoveries + artifacts |
| `/vivarium release` | release fresh founders |
| `/vivarium import <code>` | release a strain from a challenge code |
| `/vivarium race <seed> <codes>` | a deterministic species duel, verifiable anywhere |
| `/vivarium images on\|off\|auto` | inline dish painting in graphics terminals |
| `/vivarium narration off\|births\|milestones\|daily` | how much the dish speaks: births by default, full milestones, one daily report, or silence. It never talks over your agent; it speaks after the turn is over |
| `/vivarium start` | welcome briefing + the universe view |
| `/vivarium staleness` | is the living world going stale? |
| `/vivarium restart` | end the era (with a farewell picture); the next skill births a new universe |

## License

MIT - see [LICENSE](LICENSE).
