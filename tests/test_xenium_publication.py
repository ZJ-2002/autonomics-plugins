import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / 'research-adapters/cachexia-xenium/scripts/ingest.py'
SPEC = importlib.util.spec_from_file_location('xenium_publication', SOURCE)
ENTRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ENTRY)


class XeniumPublicationTests(unittest.TestCase):
    def execute(self, directory, writer):
        inputs = [directory / ('input-' + str(position)) for position in range(3)]
        for filename in inputs:
            filename.write_text(json.dumps({'test_id': 'PUBLICATION_TOY'}))
        environment = {'AUTONOMICS_INPUT' + str(position): str(filename) for position, filename in enumerate(inputs)}
        environment.update({'AUTONOMICS_OUTPUT' + str(position): str(directory / name)
                            for position, name in enumerate(ENTRY.NAMES)})
        with patch.dict(os.environ, environment), patch.object(ENTRY, 'validate'), patch.object(ENTRY, 'calculate', side_effect=writer):
            return ENTRY.main()

    @staticmethod
    def products(inputs, request, folder):
        for position, name in enumerate(ENTRY.NAMES):
            if position not in (5, 6):
                (folder / name).write_text('owned-product')
        return {'toy_format_only': True}

    def test_success_has_all_ports_and_no_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.assertEqual(self.execute(directory, self.products), 0)
            self.assertTrue(all((directory / name).is_file() for name in ENTRY.NAMES))
            self.assertFalse(list(directory.glob('xenium-publication-*')))

    def test_file_created_after_preflight_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            foreign = directory / ENTRY.NAMES[0]
            def writer(inputs, request, folder):
                foreign.write_text('foreign-late-arrival')
                return self.products(inputs, request, folder)
            self.assertEqual(self.execute(directory, writer), 1)
            self.assertEqual(foreign.read_text(), 'foreign-late-arrival')
            self.assertFalse((directory / ENTRY.NAMES[1]).exists())

    def test_failure_diagnostics_do_not_overwrite_late_foreign_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            foreign = directory / ENTRY.NAMES[5]
            def writer(inputs, request, folder):
                foreign.unlink(missing_ok=True)
                foreign.write_text('foreign-diagnostic')
                raise ValueError('injected calculation refusal')
            self.assertEqual(self.execute(directory, writer), 1)
            self.assertEqual(foreign.read_text(), 'foreign-diagnostic')
            self.assertFalse((directory / ENTRY.NAMES[0]).exists())

    def test_preexisting_dangling_outputs_are_preserved(self):
        for name in ENTRY.NAMES:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                foreign = directory / name
                foreign.symlink_to(directory / 'absent-target')
                self.assertEqual(self.execute(directory, self.products), 1)
                self.assertTrue(foreign.is_symlink())
                self.assertEqual(os.readlink(foreign), str(directory / 'absent-target'))

    def test_partial_publication_rolls_back_only_owned_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = ENTRY.publish_file
            def publisher(source, destination, published):
                if destination.name == ENTRY.NAMES[1]:
                    raise OSError('injected second publication failure')
                original(source, destination, published)
            with patch.object(ENTRY, 'publish_file', side_effect=publisher):
                self.assertEqual(self.execute(directory, self.products), 1)
            self.assertFalse((directory / ENTRY.NAMES[0]).exists())
            self.assertEqual(json.loads((directory / ENTRY.NAMES[5]).read_text())['status'], 'BLOCKED')

    def test_partial_publication_preserves_foreign_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = ENTRY.publish_file
            foreign = directory / ENTRY.NAMES[0]
            def publisher(source, destination, published):
                if destination.name == ENTRY.NAMES[1]:
                    foreign.unlink()
                    foreign.write_text('foreign-replacement')
                    raise OSError('injected replacement and failure')
                original(source, destination, published)
            with patch.object(ENTRY, 'publish_file', side_effect=publisher):
                self.assertEqual(self.execute(directory, self.products), 1)
            self.assertEqual(foreign.read_text(), 'foreign-replacement')

    def test_malformed_request_emits_failure_artifacts_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            with patch.object(ENTRY, 'decode_json', side_effect=ValueError('malformed request')):
                self.assertEqual(self.execute(directory, self.products), 1)
            self.assertEqual(json.loads((directory / ENTRY.NAMES[5]).read_text())['status'], 'BLOCKED')
            self.assertFalse((directory / ENTRY.NAMES[0]).exists())


if __name__ == '__main__':
    unittest.main()
