"""VIV-7 acceptance: on_skill_lifecycle -> automatic species birth."""
import sys, unittest, tempfile
from pathlib import Path
sys.path.insert(0, '.')

try:
    from . import hooks, birth as vbirth, world as W
    from . import universe as U
except ImportError:
    import hooks, birth as vbirth, world as W
    import universe as U
import state as vstate  # noqa: E402


class FakeState:
    def __init__(self):
        self.d = {}
    def get(self, k, default=None):
        return self.d.get(k, default)
    def set(self, k, v):
        self.d[k] = v


class FakeCtx:
    def __init__(self):
        self.state = FakeState()
        self._hooks = {}
    def register_hook(self, name, cb):
        self._hooks[name] = cb


class TempSkills:
    """Point skill_content() at a temp dir with one fake skill."""
    def __init__(self, name, body):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name) / ".hermes" / "skills" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\n\n{body}\n", encoding="utf-8")
    def __enter__(self):
        self.old = Path.home
        Path.home = lambda: Path(self.tmp.name)  # ~/.hermes/skills -> tmp
        return self
    def __exit__(self, *a):
        Path.home = self.old
        self.tmp.cleanup()


def make_live(s):
    """Drive the real seeding path so the universe is live."""
    from pathlib import Path as P
    saved = {}
    rec = U.universe_record(s)
    rec["status"] = "live"          # minimal live universe (seeding tested elsewhere)
    # PIN the universe key: without it, get_or_create_key() draws token_bytes
    # per run, so the pod's digest-picked landing cells vary — on the bare
    # test world some landings starve the pod within the 90-tick advance,
    # making the hook test flaky (deterministic key => deterministic birth).
    s.set(U.UNIVERSE_KEY, "dGVzdC1rZXktZml4ZWQtZm9yLWZsYWtlLWZyZWUtYmlydGhz")
    s.set(U.UNIVERSE_REC, rec)
    w = W.new_world(seed=11)
    saved["world"] = w.to_dict()
    s.set("world", saved["world"])
    return w


class SkillBirth(unittest.TestCase):
    def _wired(self):
        ctx = FakeCtx()
        hooks.register_hooks(ctx)
        return ctx

    def test_created_skill_births_species(self):
        ctx = self._wired()
        s = ctx.state
        make_live(s)
        with TempSkills("proof-skill", "Completely unique body content xyzzy."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="proof-skill", action="created")
        line = vstate.narration_text()
        self.assertIn("Eidos_", line)
        self.assertIn("proof-skill", line)
        self.assertIn("New species", line)
        births = s.d.get("births", {})
        self.assertIn("proof-skill", births)
        w = W.World.from_dict(s.d["world"])
        lineage = births["proof-skill"]["eidos"]
        self.assertTrue(any(c.lineage == lineage for c in w.creatures),
                        "pod must be alive in the dish after the hook")

    def test_same_skill_never_births_twice(self):
        ctx = self._wired()
        s = ctx.state
        make_live(s)
        with TempSkills("dup-skill", "Deterministic duplicate content."):
            ctx._hooks["on_skill_lifecycle"](skill_name="dup-skill", action="created")
            first = dict(s.d["births"]["dup-skill"])
            before = s.d["world"]
            ctx._hooks["on_skill_lifecycle"](skill_name="dup-skill", action="restored")
            self.assertEqual(s.d["births"]["dup-skill"], first)
            self.assertEqual(s.d["world"], before)  # world untouched on re-fire

    def test_dormant_universe_skips_birth(self):
        ctx = self._wired()
        s = ctx.state
        U.universe_record(s)  # create record, default dormant
        with TempSkills("dormant-skill", "Content while dormant."):
            ctx._hooks["on_skill_lifecycle"](
                skill_name="dormant-skill", action="created")
        self.assertNotIn("dormant-skill", s.d.get("births", {}))

    def test_first_skill_boots_the_universe(self):
        """VIV-19b: dormant universe + first skill = Big Bang from ALL skills."""
        import hooks as vhooks
        ctx = self._wired()
        s = ctx.state
        U.universe_record(s)  # dormant
        fake = [{"name": "boot-alpha", "path": "/tmp/a/SKILL.md",
                 "bytes": b"# boot-alpha\n\nAlpha content one.",
                 "is_canon": False, "kind": "private"},
                {"name": "boot-beta", "path": "/tmp/b/SKILL.md",
                 "bytes": b"# boot-beta\n\nBeta content two.",
                 "is_canon": False, "kind": "private"}]
        old = vhooks._discover_skills
        vhooks._discover_skills = lambda: fake
        try:
            ctx._hooks["on_skill_lifecycle"](
                skill_name="boot-alpha", action="created")
        finally:
            vhooks._discover_skills = old
        rec = U.universe_record(s)
        self.assertEqual(rec["status"], "live")           # universe went live
        self.assertIn("world", s.d)                       # world exists
        births = s.d.get("births", {})
        self.assertEqual(len(births), 2)                  # BOTH skills seeded
        self.assertIn("boot-alpha", births)
        self.assertIn("boot-beta", births)
        line = vstate.narration_text()
        self.assertIn("Universe born", line)              # onboarding narration

    def test_big_bang_narration_carries_media_offer(self):
        """Default-ON images: the Big Bang narration offers image delivery."""
        import hooks as vhooks
        import media_policy as vmp
        ctx = self._wired()
        s = ctx.state
        U.universe_record(s)  # dormant
        fake = [{"name": "boot-alpha", "path": "/tmp/a/SKILL.md",
                 "bytes": b"# boot-alpha\n\nAlpha content one.",
                 "is_canon": False, "kind": "private"}]
        old, oldg = vhooks._discover_skills, vmp.vterm.detect_graphics
        vhooks._discover_skills = lambda: fake
        vmp.vterm.detect_graphics = lambda: "kitty"
        try:
            ctx._hooks["on_skill_lifecycle"](
                skill_name="boot-alpha", action="created")
        finally:
            vhooks._discover_skills, vmp.vterm.detect_graphics = old, oldg
        line = vstate.narration_text()
        self.assertIn("Universe born", line)
        self.assertIn("/vivarium images off", line)   # the offer rides along
        self.assertIn("vivarium_render", line)  # agent paints via the tool

    def test_birth_narration_carries_media_offer_and_respects_off(self):
        """Birth announcement offers images when capable; never when off."""
        import media_policy as vmp
        ctx = self._wired()
        s = ctx.state
        make_live(s)
        oldg = vmp.vterm.detect_graphics
        vmp.vterm.detect_graphics = lambda: "kitty"
        try:
            with TempSkills("offer-skill", "Offer test body content zzz."):
                ctx._hooks["on_skill_lifecycle"](
                    skill_name="offer-skill", action="created")
            line = vstate.narration_text()
            self.assertIn("Eidos_", line)
            self.assertIn("/vivarium images off", line)
            self.assertIn("vivarium_render", line)   # agent paints via the tool
            while vstate.pop_narration():             # drain for the next birth
                pass
            # flip to off -> new birth, no offer
            s.set("media_pref", "ascii")
            with TempSkills("offer-skill-2", "Different body content qqq."):
                ctx._hooks["on_skill_lifecycle"](
                    skill_name="offer-skill-2", action="created")
            line2 = vstate.narration_text()
            self.assertIn("Eidos_", line2)
            self.assertNotIn("/vivarium images off", line2)
        finally:
            vmp.vterm.detect_graphics = oldg

    def test_dormant_boot_with_no_skills_narrates_waiting(self):
        import hooks as vhooks
        ctx = self._wired()
        s = ctx.state
        U.universe_record(s)
        old = vhooks._discover_skills
        vhooks._discover_skills = lambda: []
        try:
            hooks._on_skill_lifecycle(skill_name="ghost", action="installed")
        finally:
            vhooks._discover_skills = old
        self.assertEqual(U.universe_record(s)["status"], "dormant")
        self.assertIn("waiting", vstate.narration_text())

    def test_unknown_skill_is_silent(self):
        ctx = self._wired()
        s = ctx.state
        make_live(s)
        hooks._on_skill_lifecycle(skill_name="no-such-skill-xyz", action="created")
        self.assertEqual(s.d.get("births", {}), {})

    def test_digest_matches_seeding_derivation(self):
        """Same skill content -> same Eidos whether birthed or seeded."""
        s = FakeState()
        make_live(s)
        content = "identical content both paths"
        d1 = U.skill_digest(s, content)
        r = vbirth.birth_species(s, "t-skill", content,
                                 save_world=lambda w: s.set("world", w.to_dict()),
                                 load_world=lambda: W.World.from_dict(s.d["world"]),
                                 advance=0)
        self.assertEqual(r["eidos"], "Eidos_" + d1[:4].hex())


if __name__ == "__main__":
    unittest.main()


class DuplicateContent(unittest.TestCase):
    """Same content is the same species: no birth, but say so."""

    def test_find_existing_matches_by_digest(self):
        from types import SimpleNamespace
        import universe as _U
        s = FakeState()
        content = "the same body"
        digest = _U.skill_digest(s, content)
        s.d["births"] = {"probe-a": {"eidos": "Eidos_abcdef", "day": "2026-11-09",
                                     "digest_fp": digest[:8].hex()}}
        hit = vbirth.find_existing(s, content)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["eidos"], "Eidos_abcdef")

    def test_unknown_content_has_no_match(self):
        s = FakeState()
        s.d["births"] = {}
        self.assertIsNone(vbirth.find_existing(s, "never seen"))
