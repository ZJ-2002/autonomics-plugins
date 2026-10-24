import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import audit_opentargets_field_sources as proof


class FieldSourceCaptureTests(unittest.TestCase):
    def response(self, body, url):
        class Response(io.BytesIO):
            status = 200
            headers = {}
        response = Response(body)
        response.url = url
        return response

    def test_only_public_primary_source_origins_without_credentials_are_allowed(self):
        for url in [proof.DISCOVERY['api-tree'], next(iter(proof.SOURCES.values()))]:
            proof.validate_url(url)
        for url in ['http://api.github.com/repos/opentargets/pos',
                'https://api.github.com.evil.invalid/repos/opentargets/pos',
                'https://user:secret@api.github.com/repos/opentargets/pos',
                'https://raw.githubusercontent.com/other/pos/main/file',
                'https://api.github.com/repos/opentargets/pos#fragment']:
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                proof.validate_url(url)

    def test_capture_measures_hash_and_does_not_overwrite_prior_source(self):
        url = proof.DISCOVERY['api-tree']
        body = b'public source fixture'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for attempt in range(2):
                response = self.response(body, url)
                with patch.object(proof, 'build_opener') as opener, patch.object(proof.time, 'sleep'):
                    opener.return_value.open.return_value = response
                    if attempt == 0:
                        record = proof.capture('toy', url, root)
                        self.assertEqual(record['sha256'], hashlib.sha256(body).hexdigest())
                        self.assertEqual(record['bytes'], len(body))
                        self.assertTrue(record['observed_source_only_not_deployed_identity'])
                    else:
                        with self.assertRaises(FileExistsError):
                            proof.capture('toy', url, root)
                self.assertEqual((root / 'toy.source').read_bytes(), body)

    def test_wrong_final_identity_encoding_status_and_oversized_body_are_refused(self):
        url = proof.DISCOVERY['api-tree']
        for defect in ['url', 'encoding', 'status', 'bytes']:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                response = self.response(b'x' * (proof.LIMIT+1) if defect == 'bytes' else b'fixture', url)
                if defect == 'url':
                    response.url = 'https://example.invalid/'
                elif defect == 'encoding':
                    response.headers = {'Content-Encoding': 'gzip'}
                elif defect == 'status':
                    response.status = 206
                with patch.object(proof, 'build_opener') as opener, patch.object(proof.time, 'sleep'):
                    opener.return_value.open.return_value = response
                    with self.assertRaises(RuntimeError):
                        proof.capture('toy', url, Path(directory))
                self.assertFalse((Path(directory) / 'toy.source').exists())

    def test_redirect_refusal_sends_no_automatic_followup(self):
        with self.assertRaisesRegex(RuntimeError, 'redirect forbidden'):
            proof.NoRedirect().redirect_request(None, None, 302, 'Found', {}, 'https://example.invalid/')

    def weight_sources(self):
        reduced = {f'reduced_{chr(97+index)}': 0.5 for index in range(7)}
        other = {f'unit_{chr(97+index)}': 1.0 for index in range(15)}
        other['gene2phenotype'] = 1.0
        pipeline = '        datasource_weights:\n' + ''.join(
            f'          - datasourceId: {key}\n            weight: {value}\n'
            for key, value in {**reduced, **other}.items()) + '  next_section:\n'
        api = '\n'.join(f'{{id: "{key}", weight: {value}}}' for key, value in reduced.items())
        return pipeline, api

    def test_default_weights_include_identifiers_containing_digits(self):
        pipeline, api = self.weight_sources()
        result = proof.default_weights(pipeline, api)
        self.assertEqual(len(result['pipeline_weights']), 23)
        self.assertEqual(result['pipeline_weights']['gene2phenotype'], 1.0)
        self.assertTrue(result['default_configuration_values_agree'])
        self.assertTrue(result['deployed_configuration_not_verified'])

    def test_changed_missing_or_duplicate_default_weights_are_not_called_equal(self):
        pipeline, api = self.weight_sources()
        for changed_pipeline, changed_api in [
                (pipeline.replace('weight: 0.5', 'weight: 0.2', 1), api),
                (pipeline.replace('          - datasourceId: gene2phenotype\n            weight: 1.0\n', ''), api),
                (pipeline.replace('  next_section:',
                    '          - datasourceId: gene2phenotype\n            weight: 1.0\n  next_section:'), api)]:
            with self.assertRaises(RuntimeError):
                proof.default_weights(changed_pipeline, changed_api)


if __name__ == '__main__':
    unittest.main()
