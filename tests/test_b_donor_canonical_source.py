"""Keep the loaded R port scripts bound to the reviewed donor implementation.

These source checks establish neither R execution nor scientific acceptance.
"""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / "research-adapters"


def embedded_candidate(raw):
    prefix, suffix = "eval(parse(text=", "),envir=donor)"
    lines = [line for line in raw.splitlines() if line.startswith(prefix)]
    if len(lines) != 1 or not lines[0].endswith(suffix):
        raise ValueError("one complete embedded donor source required")
    return json.loads(lines[0][len(prefix):-len(suffix)])


class DonorCanonicalSource(unittest.TestCase):
    def test_all_four_loaded_wrappers_embed_actual_candidate(self):
        candidate = (ADAPTERS / "b-donor-contract/scripts/donor.R").read_text()
        for family in ("b-donor-contract", "b-donor-method"):
            for stage in ("design", "deseq2"):
                with self.subTest(family=family, stage=stage):
                    wrapper = (ADAPTERS / family / "scripts" / ("run-" + stage + ".R")).read_text()
                    self.assertEqual(embedded_candidate(wrapper), candidate)
                    self.assertIn('STAGE <- "' + stage.upper() + '"', wrapper)

    def test_duplicate_or_incomplete_embedded_source_rejected(self):
        line = 'eval(parse(text="source"),envir=donor)'
        self.assertEqual(embedded_candidate(line), "source")
        for bad in ("", line + "\n" + line, line[:-1]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                embedded_candidate(bad)


if __name__ == "__main__":
    unittest.main()
