import csv
import importlib.util
import io
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('precise_mapping', ROOT / 'research-adapters/a-carrier-concordance-v1/prepare_intake.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def payload(rows, extras=()):
    stream = io.StringIO()
    fields = ['id.exposure','id.outcome','method','role','p_primary','p_raw_exploratory',*extras]
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter='\t', lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode()


class PreciseIntakeMappingTests(unittest.TestCase):
    def setUp(self):
        self.row = {'id.exposure':'TOY_X','id.outcome':'TOY_M','method':MODULE.METHOD,
            'role':'EXPLORATORY_OVERLAP_UNRESOLVED','p_primary':'NA',
            'p_raw_exploratory':'0.12345678901234566'}

    def test_exact_lexical_cells_are_preserved_and_status_is_not_primary(self):
        actual = list(csv.DictReader(io.StringIO(MODULE.normalize_rows(payload([self.row]), 'TOY_X', 'TOY_M').decode()), delimiter='\t'))
        self.assertEqual(actual, [{**self.row, 'analysis_id':'A_X01_M06','execution_status':'ESTIMATED'}])

    def test_source_axes_roles_and_primary_cannot_be_reassigned(self):
        for key,value in [('id.exposure','OTHER'),('id.outcome','OTHER'),('role','PRIMARY'),('p_primary','0.01')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                MODULE.normalize_rows(payload([{**self.row,key:value}]), 'TOY_X','TOY_M')

    def test_missing_or_duplicate_predefined_method_is_rejected(self):
        for rows in [[{**self.row,'method':'Weighted median'}], [self.row,self.row]]:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                MODULE.normalize_rows(payload(rows),'TOY_X','TOY_M')

    def test_preexisting_identity_or_status_columns_are_rejected(self):
        for key in ['analysis_id','execution_status']:
            with self.subTest(key=key), self.assertRaises(ValueError):
                MODULE.normalize_rows(payload([{**self.row,key:'CALLER_DECLARATION'}],[key]),'TOY_X','TOY_M')
