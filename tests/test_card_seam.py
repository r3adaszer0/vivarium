"""The card must not split on the wordmark when the copy mentions a command.

An arrival card is announcement, face, copy. The head/tail seam used to be
the first occurrence of the word "vivarium" in the body, and the copy
contains `Meet it: /vivarium show Eidos_x` — so the split landed inside
that line, the headline became `Meet it: /`, and the rest of the copy
started mid-sentence under a face that was no longer where it belongs.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import acts  # noqa: E402
import birth as vbirth  # noqa: E402
import card as C  # noqa: E402
import identity as I  # noqa: E402
import world as W  # noqa: E402


class ArrivalCardSeam(unittest.TestCase):
    def setUp(self):
        self.g = W.genome_from_bytes(bytes(range(24)))
        self.res = {"eidos": "Eidos_15d6f36b", "name": "probe-user-three",
                    "genome": self.g, "pod": 4, "tick": 156}
        self.body = vbirth.announcement(self.res) + "\n" + acts.act3_for(self.res)
        self.out = C.render(self.body, 120, marker="vivarium", era=3)
        self.plain = [C.plain(ln) for ln in self.out["text"].split("\n")]

    def test_headline_is_the_announcement(self):
        hits = [ln for ln in self.plain if "New species" in ln]
        self.assertEqual(len(hits), 1)
        self.assertIn("Eidos_15d6f36b", hits[0])
        self.assertIn("from your 'probe-user-three' skill", hits[0])

    def test_command_lines_survive_intact(self):
        joined = "\n".join(self.plain)
        self.assertIn("Meet it: /vivarium show Eidos_15d6f36b", joined)
        self.assertIn("Watch it: /vivarium clip", joined)
        self.assertNotIn("Meet it: /", [ln.strip() for ln in self.plain])

    def test_face_belongs_to_the_newborn(self):
        self.assertIn(self.res["eidos"], self.out["text"].split("\n")[2])

    def test_every_gene_is_on_the_arrival_card(self):
        joined = "\n".join(self.plain)
        for gene in ("forage", "sense", "metabolism", "aggression", "mutate"):
            self.assertIn(gene, joined)

    def test_id_is_coloured_and_plain_strips_it(self):
        headline = [ln for ln in self.out["text"].split("\n")
                    if "New species" in C.plain(ln)][0]
        self.assertIn("\x1b[38;2;124;199;255m", headline)
        self.assertNotIn("\x1b[38;2;124;199;255m", C.plain(headline))


if __name__ == "__main__":
    unittest.main()
