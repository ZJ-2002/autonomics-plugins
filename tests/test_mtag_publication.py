import contextlib
import hashlib
import io
import json
import os
import shutil
import tarfile
import tempfile
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAM = os.path.join(ROOT, 'research-adapters', 'cachexia-mtag', 'scripts', 'mtag.py')
NAMESPACE = {'__name__': 'mtag_publication_controls', '__file__': PROGRAM}
with open(PROGRAM, 'rb') as source_handle:
    exec(compile(source_handle.read(), PROGRAM, 'exec'), NAMESPACE)


@contextlib.contextmanager
def patched(instance, name, replacement):
    original = getattr(instance, name)
    setattr(instance, name, replacement)
    try:
        yield
    finally:
        setattr(instance, name, original)


class MtagPublicationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='mtag-publication-toy-')
        self.outputs = [os.path.join(self.root, 'port-' + str(index)) for index in range(4)]
        files = []
        for name, payload in [('mtag_trait_1.txt', b'SYNTHETIC_TRAIT_ONE'), ('mtag_trait_2.txt', b'SYNTHETIC_TRAIT_TWO'),
                              ('mtag.log', b'SYNTHETIC_LOG'), ('mtag_sigma_hat.txt', b'1 0\n0 1\n'), ('mtag_omega_hat.txt', b'2 0\n0 2\n')]:
            filename = os.path.join(self.root, name)
            with open(filename, 'wb') as handle:
                handle.write(payload)
            files.append(filename)
        self.record = {'mode': 'MULTITRAIT', 'files': files, 'log_path': files[2],
            'result_files': [os.path.basename(filename) for filename in files[:2]], 'result_rows': [1, 1],
            'omega_artifact_status': 'OFFICIAL_FILE_PRESENT',
            'index': [{'file_name': os.path.basename(filename), 'sha256': NAMESPACE['digest'](filename), 'size_bytes': os.path.getsize(filename)} for filename in files]}

    def tearDown(self):
        shutil.rmtree(self.root)

    def publish(self, outputs=None, audit=None):
        return NAMESPACE['package_products'](self.record, self.outputs if outputs is None else outputs, {} if audit is None else audit)

    def assert_no_outputs(self, positions=None):
        for position in range(4) if positions is None else positions:
            self.assertFalse(os.path.lexists(self.outputs[position]))
        self.assertFalse(any(name.startswith('.mtag-publish-') for name in os.listdir(self.root)))

    def test_complete_raw_bytes_index_and_explicit_audit_preserved(self):
        self.publish()
        with tarfile.open(self.outputs[0], 'r') as archive:
            self.assertEqual(sorted(archive.getnames()), sorted(os.path.basename(filename) for filename in self.record['files']))
            for item in archive.getmembers():
                with open(os.path.join(self.root, item.name), 'rb') as handle:
                    self.assertEqual(archive.extractfile(item).read(), handle.read())
                self.assertEqual((item.uid, item.gid, item.mtime), (0, 0, 0))
        with open(self.outputs[1], 'rb') as handle:
            self.assertEqual(handle.read(), b'SYNTHETIC_LOG')
        with open(self.outputs[3]) as handle:
            audit = json.load(handle)
        self.assertFalse(audit['g0_granted'])
        self.assertEqual(audit['raw_artifact_index'], self.record['index'])

    def test_late_foreign_tar_is_not_overwritten(self):
        original = tarfile.open
        injected = [False]

        def competing(filename, *arguments, **keywords):
            if not injected[0]:
                injected[0] = True
                with open(self.outputs[0], 'wb') as handle:
                    handle.write(b'FOREIGN_TAR')
            return original(filename, *arguments, **keywords)

        with patched(tarfile, 'open', competing):
            with self.assertRaises((OSError, ValueError)):
                self.publish()
        with open(self.outputs[0], 'rb') as handle:
            self.assertEqual(handle.read(), b'FOREIGN_TAR')
        self.assert_no_outputs([1, 2, 3])

    def test_late_foreign_audit_preserved_and_prior_links_rolled_back(self):
        original = json.dump

        def competing(value, handle, *arguments, **keywords):
            with open(self.outputs[3], 'wb') as foreign:
                foreign.write(b'FOREIGN_AUDIT')
            return original(value, handle, *arguments, **keywords)

        with patched(json, 'dump', competing):
            with self.assertRaises((OSError, ValueError)):
                self.publish()
        with open(self.outputs[3], 'rb') as handle:
            self.assertEqual(handle.read(), b'FOREIGN_AUDIT')
        self.assert_no_outputs([0, 1, 2])

    def test_mid_packaging_failure_leaves_no_published_ports(self):
        def failing(*arguments, **keywords):
            raise IOError('Explicit synthetic log-copy failure')

        with patched(shutil, 'copyfile', failing):
            with self.assertRaises(IOError):
                self.publish()
        self.assert_no_outputs()

    def test_nonfinite_audit_failure_leaves_no_published_ports(self):
        with self.assertRaises(ValueError):
            self.publish(audit={'synthetic_invalid_value': float('nan')})
        self.assert_no_outputs()

    def test_normalized_aliases_are_rejected_before_any_write(self):
        directory = os.path.join(self.root, 'alias-parent')
        os.mkdir(directory)
        outputs = list(self.outputs)
        outputs[1] = os.path.join(directory, '..', os.path.basename(outputs[0]))
        with self.assertRaises(ValueError):
            self.publish(outputs=outputs)
        self.assert_no_outputs()

    def test_dangling_declared_port_is_not_replaced(self):
        os.symlink(os.path.join(self.root, 'missing'), self.outputs[2])
        with self.assertRaises(ValueError):
            self.publish()
        self.assertTrue(os.path.islink(self.outputs[2]))
        self.assert_no_outputs([0, 1, 3])

    def test_existing_regular_output_is_not_overwritten(self):
        with open(self.outputs[1], 'wb') as handle:
            handle.write(b'FOREIGN_LOG')
        with self.assertRaises(ValueError):
            self.publish()
        with open(self.outputs[1], 'rb') as handle:
            self.assertEqual(handle.read(), b'FOREIGN_LOG')
        self.assert_no_outputs([0, 2, 3])


if __name__ == '__main__':
    unittest.main()
