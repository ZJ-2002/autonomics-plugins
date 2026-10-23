"""Node-local requests transport policy; no HTTP or full-resource execution."""

import os
from pathlib import Path
import tomllib
import unittest
from unittest.mock import patch

import requests


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'research-adapters/cachexia-msigdb/manifest.toml'
OFFICIAL = 'https://data.broadinstitute.org/gsea-msigdb/msigdb/release/2025.1.Hs/h.all.v2025.1.Hs.symbols.gmt'


class MSigDBNetworkTests(unittest.TestCase):
    def setUp(self):
        self.manifest = tomllib.loads(MANIFEST.read_text())
        self.nodes = {node['kind']: node for node in self.manifest['nodes']}
        self.policy = self.nodes['cachexia_msigdb_gmt']['command']['env']

    def test_policy_is_online_node_local(self):
        self.assertEqual(self.policy, {'CACHEXIA_GMT_MODE': 'fetch',
                                      'no_proxy': 'data.broadinstitute.org',
                                      'NO_PROXY': 'data.broadinstitute.org'})
        self.assertEqual(self.nodes['cachexia_gmt_import']['command']['env'],
                         {'CACHEXIA_GMT_MODE': 'parse'})
        self.assertEqual(self.nodes['cachexia_msigdb_gmt']['resources']['network'], 'egress')
        self.assertEqual(self.nodes['cachexia_gmt_import']['resources']['network'], 'isolated')

    def test_requests_effective_proxy_matrix_and_parent_unchanged(self):
        before = dict(os.environ)
        cases = 0
        for spelling in ('lower', 'upper', 'both'):
            proxies = {}
            if spelling in ('lower', 'both'):
                proxies.update(http_proxy='http://127.0.0.1:1', https_proxy='http://127.0.0.1:1',
                               all_proxy='http://127.0.0.1:1')
            if spelling in ('upper', 'both'):
                proxies.update(HTTP_PROXY='http://127.0.0.1:2', HTTPS_PROXY='http://127.0.0.1:2',
                               ALL_PROXY='http://127.0.0.1:2')
            for exceptions in ({}, {'no_proxy': '', 'NO_PROXY': ''},
                               {'no_proxy': 'localhost,old.example', 'NO_PROXY': 'upper.example'}):
                inherited = dict(proxies, **exceptions)
                with self.subTest(spelling=spelling, exceptions=exceptions):
                    with patch.dict(os.environ, inherited, clear=True):
                        self.assertTrue(requests.utils.get_environ_proxies(OFFICIAL))
                    with patch.dict(os.environ, dict(inherited, **self.policy), clear=True):
                        with requests.Session() as session:
                            settings = session.merge_environment_settings(OFFICIAL, {}, True, None, None)
                            self.assertEqual(settings['proxies'], {})
                            self.assertTrue(settings['verify'])
                        # Unrelated domains still use inherited proxies; no global bypass.
                        self.assertTrue(requests.utils.get_environ_proxies('https://example.invalid/'))
                    cases += 1
        self.assertEqual(cases, 9)
        self.assertEqual(dict(os.environ), before)


if __name__ == '__main__':
    unittest.main()
