from pathlib import Path
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
IMAGE = 'ghcr.io/zj-2002/mrlap-official@sha256:e6e10cddfa1cba8046ee6fbc1492b94cbd70d66b097f5f415845d56f9f925434'
RETIRED_DIGEST = '78f195b862a3b7c5f8d96a96576cfb2c66b08f9bd31a739da59a017726cd063d'
MANIFESTS = [
    'research-adapters/frozen-a-family-adjustment/manifest.toml',
    'research-adapters/frozen-a-harmonisation/manifest.toml',
    'research-adapters/cachexia-mrlap/manifest.toml',
    'plugins/r-stats/manifest.toml',
    'plugins/donor-composition-official/manifest.toml',
    'plugins/r-stats-lm/manifest.toml',
    'plugins/twosamplemr-v432-a/manifest.toml',
]


class SharedMrlapImageReferenceTests(unittest.TestCase):
    def test_all_seven_shared_dependencies_use_the_qualified_reference(self):
        for relative in MANIFESTS:
            with self.subTest(manifest=relative):
                document = tomllib.loads((ROOT / relative).read_text())
                self.assertEqual(document['image']['reference'], IMAGE)

    def test_no_active_source_manifest_reintroduces_the_retired_digest(self):
        retired = []
        for directory in [ROOT / 'plugins', ROOT / 'research-adapters']:
            for path in directory.rglob('manifest.toml'):
                if RETIRED_DIGEST in path.read_text():
                    retired.append(path.relative_to(ROOT).as_posix())
        self.assertEqual(retired, [])


if __name__ == '__main__':
    unittest.main()
