import gzip
from pathlib import Path
import tempfile
import unittest

from tools import audit_ldsc_panel_structure as audit


class PanelStructureTests(unittest.TestCase):
    def test_literal_unique_score_coordinates_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scores.gz'
            with gzip.open(path,'wt') as stream:
                stream.write('CHR SNP BP L2\n1 rs001 123 1.2\n1 rs002 234 3.4\n')
            self.assertEqual(audit.read_scores(path,1),{'rs001':123,'rs002':234})

    def test_wrong_chromosome_duplicate_and_nonfinite_rows_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scores.gz'
            for rows in ['2 rs1 123 1.2\n','1 rs1 123 1.2\n1 rs1 123 1.2\n','1 rs1 123 NaN\n','']:
                with self.subTest(rows=rows):
                    with gzip.open(path,'wt') as stream:
                        stream.write('CHR SNP BP L2\n'+rows)
                    with self.assertRaises(RuntimeError):
                        audit.read_scores(path,1)

    def test_axis_differences_are_reported_without_filtering_or_coordinate_changes(self):
        first={'rs1':10,'rs2':20}
        second={'rs1':10,'rs3':30}
        self.assertEqual(audit.compare_axes(first,second),dict(shared=1,reference_only=1,weight_only=1))
        self.assertEqual(first,{'rs1':10,'rs2':20})
        for other in [{'rs1':11},{'rs3':30}]:
            with self.assertRaises(RuntimeError):
                audit.compare_axes(first,other)


if __name__ == '__main__':
    unittest.main()
