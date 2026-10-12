"""Transport mutations cannot turn imported complete methods into new methods."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_frozen_genetic import FAMILIES, check_family, check_all

ROOT = Path(__file__).resolve().parents[1]


class FrozenGeneticTransportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.family = Path(self.temporary.name)/'mr-contract'
        shutil.copytree(ROOT/'research-adapters/mr-contract', self.family)

    def test_all_exact_methods_and_full_assembled_programs_are_present_without_writes(self):
        before = {p.relative_to(ROOT).as_posix(): p.read_bytes() for name in FAMILIES
                  for p in (ROOT/'research-adapters'/name).rglob('*') if p.is_file()}
        reports = check_all(ROOT)
        self.assertEqual(len(reports), 9)
        self.assertEqual(sum(len(r['kinds']) for r in reports), 10)
        self.assertTrue(all(not r['auto_enable'] and not r['scientific_authorization'] for r in reports))
        after = {p.relative_to(ROOT).as_posix(): p.read_bytes() for name in FAMILIES
                 for p in (ROOT/'research-adapters'/name).rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_changed_component_refuses_before_any_output_write(self):
        component = self.family/'components/study_plugins/shared/gwas-normalization-receipt.R'
        wrapper = self.family/'scripts/run-mr.sh'; before = wrapper.read_bytes()
        component.write_bytes(component.read_bytes()+b'\n# drift\n')
        with self.assertRaisesRegex(ValueError, 'source identity differs'):
            check_family(self.family)
        self.assertEqual(wrapper.read_bytes(), before)

    def test_updated_local_sha_cannot_mislabel_changed_bytes_as_the_original_git_blob(self):
        component = self.family/'components/study_plugins/shared/gwas-normalization-receipt.R'
        raw = component.read_bytes()+b'\n# changed component\n'; component.write_bytes(raw)
        path = self.family/'component-source.json'; lock = json.loads(path.read_text())
        row = lock['component_files']['study_plugins/shared/gwas-normalization-receipt.R']
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        path.write_text(json.dumps(lock))
        with self.assertRaisesRegex(ValueError, 'source identity differs'):
            check_family(self.family)

    def test_missing_component_refuses_complete_program_transport(self):
        (self.family/'components/study_plugins/mr-contract/scripts/mr.R').unlink()
        with self.assertRaisesRegex(ValueError, 'component universe differs'):
            check_family(self.family)

    def test_aliased_component_is_not_an_original_regular_source(self):
        component = self.family/'components/study_plugins/mr-contract/scripts/mr.R'
        raw = component.read_bytes(); component.unlink()
        foreign = Path(self.temporary.name)/'foreign.R'; foreign.write_bytes(raw)
        component.symlink_to(foreign)
        with self.assertRaisesRegex(ValueError, 'unaliased component'):
            check_family(self.family)

    def test_extra_component_refuses_partial_universe_acceptance(self):
        (self.family/'components/extra.R').write_text('extra component')
        with self.assertRaisesRegex(ValueError, 'component universe differs'):
            check_family(self.family)

    def test_changed_standalone_program_is_not_repaired_or_accepted(self):
        wrapper = self.family/'scripts/run-mr.sh'; changed = wrapper.read_bytes()+b'\n# drift\n'
        wrapper.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, 'source identity differs'):
            check_family(self.family)
        self.assertEqual(wrapper.read_bytes(), changed)

    def test_changed_manifest_does_not_silently_replace_image_or_interface(self):
        path = self.family/'manifest.toml'
        path.write_bytes(path.read_bytes().replace(b'0.7.9', b'0.7.8'))
        with self.assertRaisesRegex(ValueError, 'source identity differs'):
            check_family(self.family)

    def test_source_lock_cannot_grant_scientific_permission_or_auto_enable(self):
        path = self.family/'component-source.json'; original = json.loads(path.read_text())
        for key in ['scientific_authorization', 'auto_enable']:
            with self.subTest(key=key):
                value = {**original, key: True}; path.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, 'unapproved'):
                    check_family(self.family)
        path.write_text(json.dumps(original))
        self.assertEqual(check_family(self.family)['source_commit'], original['source_commit'])

    def test_manifest_program_set_must_be_complete_even_with_other_valid_sources(self):
        path = self.family/'component-source.json'; value = json.loads(path.read_text())
        value['programs']['unexpected.sh'] = value['programs']['scripts/run-mr.sh']
        path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, 'program universe differs'):
            check_family(self.family)
