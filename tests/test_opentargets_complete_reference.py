import unittest

from tools import probe_opentargets_complete_reference as probe


class OfficialPaginationReferenceTests(unittest.TestCase):
    def value(self, count, rows):
        return dict(disease=dict(id=probe.CONTROL, associatedTargets=dict(count=count, rows=rows)))

    def test_complete_shapes_do_not_remove_or_reinterpret_duplicate_rows(self):
        row = dict(target=dict(id="ENSG_ONE"), score=.01)
        total, rows = probe.check_page(self.value(2, [row, row.copy()]), 0, None)
        self.assertEqual(total, 2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["target"]["id"], rows[1]["target"]["id"])

    def test_parent_count_drift_and_truncation_are_not_accepted(self):
        row = dict(target=dict(id="ENSG_ONE"), score=.01)
        cases = [(self.value(2, [row]), 0, None), (self.value(1, [row]), 0, 2),
                 (dict(disease=dict(id="WRONG", associatedTargets=dict(count=1, rows=[row]))), 0, None)]
        for value, index, count in cases:
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                probe.check_page(value, index, count)

    def test_boolean_counts_nonfinite_scores_and_missing_identity_refuse(self):
        values = [self.value(True, []), self.value(1, [dict(target=dict(id="ENSG_ONE"), score=float("nan"))]),
                  self.value(1, [dict(target=dict(id="ENSG_ONE"), score=True)]),
                  self.value(1, [dict(target={}, score=.1)])]
        for value in values:
            with self.assertRaises(RuntimeError):
                probe.check_page(value, 0, None)


if __name__ == "__main__":
    unittest.main()
