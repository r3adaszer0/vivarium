"""VIV-104: the featured "latest birth" card must follow the newest birth
EVENT, not dict insertion order.

A re-birth (VIV-61: a skill with an older-era registry row births again)
RE-ASSIGNS an existing key in the births dict — Python keeps a re-assigned
key's original position. ``list(births.items())[-1]`` therefore returns
whichever NEW-name skill was inserted last, and the featured card pinned
the second-to-last birth forever (the reported bug: "first skill flips,
second doesn't"). The fix is one shared selector, driven by a monotonic
seq stamped into every birth record at write time — gallery build-time and
the serve live poll both call it, so the two data paths cannot diverge.
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import birth as vbirth         # noqa: E402
import gallery as vgal         # noqa: E402
import hooks as vhooks         # noqa: E402
import seeding as S            # noqa: E402
import tools as T              # noqa: E402
from test_birth import FakeCtx, FakeState, TempSkills, make_live  # noqa: E402


def _rec(eidos, era, seq=None, **extra):
    g = {"forage": 1.2, "aggression": 0.9, "metabolism_mult": 1.1,
         "sense": 1.4, "mutate": 1.0, "dispersal": 0.5, "hue": 0.31}
    r = {"eidos": eidos, "era": era, "genome": dict(g),
         "day": "2026-11-12"}
    r.update(extra)
    if seq is not None:
        r["seq"] = seq
    return r


class TestNewestBirthSelector(unittest.TestCase):
    """birth.newest_birth — the ONE selection both data paths share."""

    def test_rebirth_of_older_key_beats_last_inserted(self):
        births = {"probe-user-one": _rec("Eidos_0d421910", 1, seq=1),
                  "probe-user-two": _rec("Eidos_9934ccb0", 2, seq=2),
                  "probe-user-three": _rec("Eidos_f5d9e057", 3, seq=3)}
        births["probe-user-one"] = _rec("Eidos_0d421910", 4, seq=4)  # re-birth
        # the trap itself: dict position still points at the last INSERTED
        self.assertEqual(list(births.items())[-1][0], "probe-user-three")
        name, rec = vbirth.newest_birth(births)
        self.assertEqual((name, rec["eidos"]),
                         ("probe-user-one", "Eidos_0d421910"))

    def test_stamped_rows_rank_above_legacy_rows(self):
        births = {"old-a": _rec("Eidos_aaaaaaaa", 3),       # legacy, no seq
                  "old-b": _rec("Eidos_bbbbbbbb", 7),       # legacy, newer era
                  "new": _rec("Eidos_cccccccc", 2, seq=1)}  # stamped
        name, _ = vbirth.newest_birth(births)
        self.assertEqual(name, "new")

    def test_legacy_rows_tiebreak_by_era_then_insertion(self):
        # even with NO seq anywhere, a re-birth updates its record's era,
        # so data still beats dict position for pre-VIV-104 registries
        births = {"probe-user-one": _rec("Eidos_0d421910", 4),
                  "probe-user-two": _rec("Eidos_9934ccb0", 2),
                  "probe-user-three": _rec("Eidos_f5d9e057", 3)}
        name, _ = vbirth.newest_birth(births)
        self.assertEqual(name, "probe-user-one")

    def test_empty_and_malformed_registries(self):
        self.assertIsNone(vbirth.newest_birth({}))
        self.assertIsNone(vbirth.newest_birth(None))
        self.assertIsNone(vbirth.newest_birth([]))      # pre-VIV-7 list shape
        births = {"junk": "not-a-dict", "ok": _rec("Eidos_dddddddd", 1, seq=2)}
        self.assertEqual(vbirth.newest_birth(births)[0], "ok")

    def test_next_birth_seq(self):
        self.assertEqual(vbirth.next_birth_seq({}), 1)
        self.assertEqual(vbirth.next_birth_seq({"a": _rec("E", 1, seq=7)}), 8)
        self.assertEqual(vbirth.next_birth_seq({"a": "junk"}), 1)


class TestWritersStampSeq(unittest.TestCase):
    """Every path that writes a birth record must stamp the monotonic seq."""

    def test_skill_births_stamp_increasing_seq(self):
        ctx = FakeCtx()
        vhooks.register_hooks(ctx)
        s = ctx.state
        make_live(s)
        with TempSkills("seq-skill-a", "Unique content alpha for seq test."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="seq-skill-a", action="created")
        with TempSkills("seq-skill-b", "Unique content beta for seq test."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="seq-skill-b", action="created")
        births = s.d["births"]
        self.assertIsInstance(births["seq-skill-a"]["seq"], int)
        self.assertGreater(births["seq-skill-b"]["seq"],
                           births["seq-skill-a"]["seq"])

    def test_older_era_rebirth_stamps_a_fresh_seq_and_wins(self):
        ctx = FakeCtx()
        vhooks.register_hooks(ctx)
        s = ctx.state
        make_live(s)
        # a registry row from an older era, inserted BEFORE the newer
        # skill's birth — dict insertion order puts the newer name last
        s.d["universe"]["era"] = 1
        s.d.setdefault("births", {})["rebirth-skill"] = {
            "eidos": "Eidos_deadbeef", "day": "2026-11-01", "pod": 4,
            "digest_fp": "0123456789abcdef", "era": 1}
        with TempSkills("newer-skill", "The newest new-name birth so far."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="newer-skill", action="created")
        # VIV-61: an older-era registry row does not block a re-birth
        s.d["universe"]["era"] = 2
        with TempSkills("rebirth-skill", "Brand new content for era two."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="rebirth-skill", action="created")
        births = s.d["births"]
        self.assertEqual(births["rebirth-skill"]["era"], 2)
        name, rec = vbirth.newest_birth(births)
        self.assertEqual(name, "rebirth-skill")
        self.assertEqual(rec["seq"],
                         max(int(r["seq"]) for r in births.values()))
        # and the old selector would have pinned the wrong Hermi: the
        # re-birth kept its old dict position, so insertion order still
        # points at the newer-NAME skill
        self.assertEqual(list(births.items())[-1][0], "newer-skill")

    def test_big_bang_seeding_stamps_seq_in_seed_order(self):
        def sk(name, canon):
            return {"name": name, "path": "/x", "is_canon": canon,
                    "kind": "canon" if canon else "private",
                    "bytes": f"content of {name}".encode()}
        s = FakeState()
        out = S.seed(s, [sk("canon-a", True), sk("canon-b", True),
                         sk("priv-a", False), sk("priv-b", False)],
                     save_world=lambda w: None)
        self.assertIsNotNone(out)
        births = s.d["births"]
        seqs = [births[n]["seq"] for n in
                ("canon-a", "canon-b", "priv-a", "priv-b")]
        self.assertTrue(all(isinstance(v, int) for v in seqs))
        self.assertEqual(seqs, sorted(seqs), "seed order is birth order")
        name, _ = vbirth.newest_birth(births)
        self.assertEqual(name, "priv-b")   # the last seeded species


class _DictState:
    """Minimal state handle for build_page (it only calls .get)."""

    def __init__(self, d):
        self.d = d

    def get(self, k, default=None):
        return self.d.get(k, default)


class TestFeaturedCard(unittest.TestCase):
    """Build-time path: gallery.build_page must feature the newest EVENT."""

    def _state(self, births):
        return _DictState({"universe": {"era": 4, "status": "live",
                                        "key_fp": "abcdef12"},
                           "births": births, "fossils": [], "curve": []})

    def test_build_time_card_names_the_rebirth(self):
        births = {"probe-user-one": _rec("Eidos_0d421910", 4, seq=4),
                  "probe-user-three": _rec("Eidos_f5d9e057", 3, seq=3)}
        html = vgal.build_page("/nonexistent", "", st=self._state(births))
        card = html.split('class="latest"')[1].split("</a>")[0]
        self.assertIn("Eidos_0d421910", card)
        self.assertIn('data-seq="4"', card)
        self.assertNotIn("Eidos_f5d9e057", card)

    def test_legacy_record_still_renders_a_card(self):
        html = vgal.build_page(
            "/nonexistent", "",
            st=self._state({"s": _rec("Eidos_0d421910", 2)}))
        self.assertIn('data-seq=""', html)
        self.assertIn("Eidos_0d421910", html.split('class="latest"')[1])

    def test_page_carries_the_create_and_seq_guard_js(self):
        births = {"s": _rec("Eidos_0d421910", 2, seq=3)}
        html = vgal.build_page("/nonexistent", "", st=self._state(births))
        self.assertIn("card.dataset.seq!==seq", html)
        self.assertIn("querySelector('.nowside')", html)


class TestLivePollPayload(unittest.TestCase):
    """Serve path: the per-poll payload must use the same selector."""

    def test_payload_follows_the_rebirth(self):
        births = {"probe-user-one": _rec("Eidos_0d421910", 4, seq=4),
                  "probe-user-three": _rec("Eidos_f5d9e057", 3, seq=3)}
        payload = T._latest_birth_payload(births, frozenset())
        self.assertEqual(payload["eidos"], "Eidos_0d421910")
        self.assertEqual(payload["skill"], "probe-user-one")
        self.assertEqual(payload["seq"], 4)
        self.assertIn("<svg", payload["face_svg"])

    def test_payload_empty_registry_is_none(self):
        self.assertIsNone(T._latest_birth_payload({}, frozenset()))
        self.assertIsNone(T._latest_birth_payload(None, frozenset()))

    def test_payload_extinct_face_is_grayed_not_absent(self):
        births = {"gone": _rec("Eidos_0d421910", 4, seq=4)}
        payload = T._latest_birth_payload(births, frozenset({"0d421910"}))
        self.assertIn("<svg", payload["face_svg"])


class TestFaceSvgNeverEmpty(unittest.TestCase):
    """The half-morph: an empty face_svg kept the OLD face under a new name."""

    def test_unrenderable_genomes_degrade_to_a_face(self):
        for bad in (None, "junk", 42, [], {"hue": []}, {"hue": "nope"}):
            face = vgal._face_svg(bad, False, 64)
            self.assertTrue(face.lstrip().startswith("<svg"), repr(bad))
            self.assertIn("</svg>", face)
        for bad in (None, {"hue": []}):
            face = vgal._face_svg(bad, True, 64)   # dead faces too
            self.assertTrue(face.lstrip().startswith("<svg"), repr(bad))

    def test_fallback_face_is_deterministic(self):
        self.assertEqual(vgal._face_svg(None, False, 64),
                         vgal._face_svg(None, False, 64))

    def test_real_genome_still_gets_the_real_glyph(self):
        good = _rec("Eidos_abcd1234", 1)["genome"]
        self.assertIn("<rect", vgal._face_svg(good, False, 64))
        # the fallback is a DIFFERENT deterministic face, not the real glyph
        self.assertNotEqual(vgal._face_svg(good, False, 64),
                            vgal._face_svg(None, False, 64))


if __name__ == "__main__":
    unittest.main()
