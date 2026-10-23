from pathlib import Path
import subprocess
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
BASE_REVISION = '3568272020d75be43d004f6b59f47fc9bec2e718'
REFERENCES = {
    'survey': 'ghcr.io/zj-2002/survey-official@sha256:6f3e6f417912b7fb2c2b344ceaa11ff6031cde7848740caf6450c4366b5fbc61',
    'mice': 'ghcr.io/zj-2002/mice-official@sha256:ff4c166b89842d9bfbcf8d0f8227d05057a3ae57a668d374374a60db1e425516',
    'lcmm': 'ghcr.io/zj-2002/lcmm-official@sha256:dd7f8a68d27a1002d5f6b004ca2ad24fc92cc7db43773500963363f92f8828d5',
}


def frozen_bytes(relative_path):
    return subprocess.run(
        ['git', '-C', str(ROOT), 'show', f'{BASE_REVISION}:{relative_path}'],
        check=True, capture_output=True,
    ).stdout


class ConditionalRegistryBindingTests(unittest.TestCase):
    def test_only_the_exact_image_reference_bytes_change(self):
        for family, target_reference in REFERENCES.items():
            with self.subTest(family=family):
                relative_path = f'research-adapters/cachexia-{family}/manifest.toml'
                original = frozen_bytes(relative_path)
                original_document = tomllib.loads(original.decode('utf-8'))
                original_reference = original_document['image']['reference'].encode('utf-8')
                self.assertEqual(original.count(original_reference), 1)
                expected = original.replace(original_reference, target_reference.encode('utf-8'), 1)
                self.assertEqual((ROOT / relative_path).read_bytes(), expected)

    def test_complete_toml_contract_is_preserved_except_reference(self):
        for family, target_reference in REFERENCES.items():
            with self.subTest(family=family):
                relative_path = f'research-adapters/cachexia-{family}/manifest.toml'
                original = tomllib.loads(frozen_bytes(relative_path).decode('utf-8'))
                current = tomllib.loads((ROOT / relative_path).read_text(encoding='utf-8'))
                self.assertEqual(current['image']['reference'], target_reference)
                original['image']['reference'] = target_reference
                self.assertEqual(current, original)

    def test_declared_entrypoints_and_synthetic_scope_guards_are_unchanged(self):
        for family in REFERENCES:
            with self.subTest(family=family):
                adapter = Path('research-adapters') / f'cachexia-{family}'
                manifest = tomllib.loads(frozen_bytes(adapter / 'manifest.toml').decode('utf-8'))
                scripts = {node['command']['script_file'] for node in manifest['nodes']}
                self.assertTrue(scripts)
                frozen_scripts = []
                for script in sorted(scripts):
                    relative_path = adapter / script
                    original = frozen_bytes(relative_path)
                    self.assertEqual((ROOT / relative_path).read_bytes(), original, str(relative_path))
                    frozen_scripts.append(original)
                combined = b'\n'.join(frozen_scripts)
                for marker in (
                    b'SYNTHETIC_TECHNICAL_INPUT',
                    b'TECHNICAL_ONLY_NOT_G0',
                    b'NOT_GRANTED',
                ):
                    self.assertIn(marker, combined)


if __name__ == '__main__':
    unittest.main()
