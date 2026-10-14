import unittest

from tools.audit_study_software_surfaces import FIELDS, rows


class SoftwareSurfaceTests(unittest.TestCase):
    def fixture(self):
        return ('\t'.join(FIELDS)+'\n'+''.join(f'method{index}\tpurpose\t\t\t\tNOT_IMPLEMENTATION_LOCKED\n' for index in range(18))).encode()

    def test_blank_version_is_not_invented_or_promoted(self):
        records=rows(self.fixture())
        self.assertEqual(len(records),18)
        self.assertTrue(all(record['version_or_commit']=='' for record in records))
        self.assertTrue(all(record['status']=='NOT_IMPLEMENTATION_LOCKED' for record in records))

    def test_missing_duplicate_and_ragged_rows_refuse(self):
        original=self.fixture()
        for payload in [original.rsplit(b'\n',2)[0]+b'\n', original.replace(b'method17',b'method16'),
                        original.replace(b'method17\tpurpose\t\t\t\t',b'method17\tpurpose\t\t\t')]:
            with self.assertRaises(RuntimeError):rows(payload)


if __name__=='__main__':unittest.main()
