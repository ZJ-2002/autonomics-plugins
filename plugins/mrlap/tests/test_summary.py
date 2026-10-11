import copy
import csv
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import verify_summary as comparison


class SummaryTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.root = Path(self.scratch.name)
        self.reference = []
        for index, (tag,label) in enumerate(comparison.EDGES):
            row = {field:'0.01' for field in comparison.FIELDS}
            row.update(edge=tag,rg_se='NA')
            self.reference.append(row)
            output = copy.deepcopy(row)
            output['edge']=label
            directory = self.root/('edge_'+str(index))
            directory.mkdir()
            self.write(directory/'summary.tsv',[output])
        self.write(self.root/'reference.tsv',self.reference)

    def tearDown(self):
        self.scratch.cleanup()

    def write(self, filename, rows, fields=None):
        with filename.open('w') as handle:
            writer = csv.DictWriter(handle,fieldnames=fields or ['edge']+comparison.FIELDS,delimiter='\t')
            writer.writeheader()
            writer.writerows(rows)

    def verify(self):
        return comparison.verify(self.root/'reference.tsv',self.root)

    def test_complete_census_includes_explicit_missing_not_51_finite_numbers(self):
        record = self.verify()
        self.assertEqual(record['summary_entries_verified'],51)
        self.assertEqual(record['finite_numeric_comparisons'],48)
        self.assertEqual(record['explicit_missing_rg_se_entries'],3)

    def test_missing_reference_edge(self):
        self.write(self.root/'reference.tsv',self.reference[:2])
        with self.assertRaises(ValueError): self.verify()

    def test_duplicate_reference_edge(self):
        self.reference[2]['edge']='XM'
        self.write(self.root/'reference.tsv',self.reference)
        with self.assertRaises(ValueError): self.verify()

    def test_extra_reference_edge(self):
        self.write(self.root/'reference.tsv',self.reference+[self.reference[0]])
        with self.assertRaises(ValueError): self.verify()

    def test_missing_numeric_field(self):
        rows = [{name:value for name,value in row.items() if name!='mr_corrected'} for row in self.reference]
        self.write(self.root/'reference.tsv',rows,['edge']+[field for field in comparison.FIELDS if field!='mr_corrected'])
        with self.assertRaises(ValueError): self.verify()

    def test_empty_output(self):
        self.write(self.root/'edge_0/summary.tsv',[])
        with self.assertRaises(ValueError): self.verify()

    def test_duplicate_output_rows(self):
        rows = comparison.read_rows(self.root/'edge_0/summary.tsv')
        self.write(self.root/'edge_0/summary.tsv',rows+rows)
        with self.assertRaises(ValueError): self.verify()

    def test_wrong_output_edge(self):
        rows = comparison.read_rows(self.root/'edge_0/summary.tsv')
        rows[0]['edge']='Monocyte->GripStrength'
        self.write(self.root/'edge_0/summary.tsv',rows)
        with self.assertRaises(ValueError): self.verify()

    def test_both_infinite_is_not_a_match(self):
        expected = copy.deepcopy(self.reference[0]); actual = copy.deepcopy(expected)
        expected['mr_corrected']=actual['mr_corrected']='Inf'
        with self.assertRaises(ValueError): comparison.compare_rows(expected,actual)

    def test_both_nan_is_not_a_match(self):
        expected = copy.deepcopy(self.reference[0]); actual = copy.deepcopy(expected)
        expected['mr_corrected']=actual['mr_corrected']='NaN'
        with self.assertRaises(ValueError): comparison.compare_rows(expected,actual)

    def test_primary_na_is_not_an_estimable_match(self):
        expected = copy.deepcopy(self.reference[0]); actual = copy.deepcopy(expected)
        expected['mr_corrected']=actual['mr_corrected']='NA'
        with self.assertRaises(ValueError): comparison.compare_rows(expected,actual)

    def test_frozen_tolerance_is_not_relaxed(self):
        expected = copy.deepcopy(self.reference[0]); actual = copy.deepcopy(expected)
        actual['mr_corrected']='0.010000000002'
        with self.assertRaises(ValueError): comparison.compare_rows(expected,actual)


if __name__=='__main__':
    unittest.main()
