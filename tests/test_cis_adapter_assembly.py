"""Mutations must not silently alter the individually accepted R components."""
import shutil
from pathlib import Path
import tempfile
import unittest

from tools.assemble_cis_mr import assembled, check


class CisAssemblyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.family = Path(self.directory.name) / 'family'
        shutil.copytree(Path(__file__).resolve().parents[1] / 'research-adapters/cis-mr-declared', self.family)

    def test_original_qualified_components_and_generated_entry_agree(self):
        self.assertEqual(len(check(self.family)), 64)

    def test_component_mutation_refuses_before_any_generated_write(self):
        target = self.family / 'scripts/cis_mr.R'; original = target.read_bytes()
        component = self.family / 'components/research_cis_mr.R'
        component.write_bytes(component.read_bytes().replace(b'psi = 0', b'psi = 1'))
        with self.assertRaisesRegex(ValueError, 'source identity differs'):
            assembled(self.family)
        self.assertEqual(target.read_bytes(), original)

    def test_missing_or_aliased_component_does_not_create_partial_program(self):
        path = self.family / 'components/research_cis_ld.R'; original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'regular component'):
            assembled(self.family)
        foreign = self.family / 'foreign.R'; foreign.write_bytes(original); path.symlink_to(foreign)
        with self.assertRaisesRegex(ValueError, 'regular component'):
            assembled(self.family)

    def test_runnable_script_cannot_diverge_from_unmodified_component_lock(self):
        path = self.family / 'scripts/cis_mr.R'
        path.write_bytes(path.read_bytes().replace(b'WALD_FIRST_ORDER', b'DEFAULT_WALD'))
        with self.assertRaisesRegex(ValueError, 'Runnable cis adapter differs'):
            check(self.family)
