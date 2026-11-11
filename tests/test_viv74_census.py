"""VIV-74: the census rides every arrival card.

The user spec, verbatim: after act-4, every new skill Hermes learns must
show the Eidos id, the name, the dish, the Hermi face with the
attributes, and UNDER the image the tick, how many alive, the lineages
and the top coloured - plus the /vivarium help, /vivarium explain and
/vivarium status pointers. The census used to print ONLY on the
two-column dish layout; on a narrow or non-painting surface the dish
dropped out and the numbers vanished with it.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import acts  # noqa: E402
import birth as vbirth  # noqa: E402
import card as C  # noqa: E402
import world as W  # noqa: E402

LIVE = {"tick": 5844, "alive": 62, "lineages": 3, "lineages_total": 12,
        "coloured": 50, "grey": 12}


def _body():
    g = W.genome_from_bytes(bytes(range(24)))
    res = {"eidos": "Eidos_01eea05e", "name": "probe-user-five",
           "genome": g, "pod": 4, "tick": 5844}
    return vbirth.announcement(res) + "\n" + acts.act3_for(res, arrival=False)


class CensusEverywhere(unittest.TestCase):
    """tick/alive/lineages/top-coloured survive the no-dish layout."""

    def test_census_on_dish_card(self):
        out = C.render(_body(), 120, marker="vivarium", live=LIVE,
                       era=3)
        plain = C.plain(out["text"])
        for needle in ("tick 5844", "62 alive", "lineages",
                       "top 8 coloured"):
            self.assertIn(needle, plain)

    def test_census_on_no_dish_card(self):
        out = C.render(_body(), 100, marker="vivarium", live=LIVE,
                       dish=False, era=3)
        plain = C.plain(out["text"])
        for needle in ("tick 5844", "62 alive", "lineages",
                       "top 8 coloured"):
            self.assertIn(needle, plain)

    def test_census_with_clean_top(self):
        live = dict(LIVE, grey=0)
        out = C.render(_body(), 100, marker="vivarium", live=live,
                       dish=False, era=3)
        plain = C.plain(out["text"])
        self.assertIn("12 lineages", plain)
        self.assertNotIn("top 8 coloured", plain,
                         "no greys -> no paint rule needed")

    def test_commands_pointers_survive(self):
        out = C.render(_body(), 100, marker="vivarium", live=LIVE,
                       dish=False, era=3)
        plain = C.plain(out["text"])
        for needle in ("/vivarium help", "/vivarium explain",
                       "/vivarium status"):
            self.assertIn(needle, plain)

    def test_face_and_bars_on_routine_arrival(self):
        out = C.render(_body(), 100, marker="vivarium", live=LIVE,
                       dish=False, era=3)
        text = out["text"]
        self.assertIn("Eidos_01eea05e", text)
        for gene in ("forage", "sense", "metabolism", "aggression",
                     "mutate", "dispersal"):
            self.assertIn(gene, text)
        # one line of copy, not the export/race pitch again
        self.assertNotIn("/vivarium export", text)
        self.assertNotIn("/vivarium race", text)


if __name__ == "__main__":
    unittest.main()
