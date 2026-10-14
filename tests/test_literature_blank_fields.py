import unittest

from tools.prove_literature_blank_fields import test_summary


class LiteratureBlankProofTests(unittest.TestCase):
    def test_real_success_and_failure_summaries_remain_distinct(self):
        self.assertEqual(test_summary('test result: ok. 9 passed; 0 failed; 0 ignored;'),
                         dict(passed=9, failed=0, ignored=0))
        self.assertEqual(test_summary('test result: FAILED. 0 passed; 1 failed; 0 ignored;'),
                         dict(passed=0, failed=1, ignored=0))

    def test_missing_duplicate_zero_and_ignored_summaries_are_not_passes(self):
        for text in [
            '',
            'test result: ok. 0 passed; 0 failed; 0 ignored;',
            'test result: ok. 1 passed; 0 failed; 1 ignored;',
            'test result: ok. 1 passed; 0 failed; 0 ignored;\n' * 2,
        ]:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                test_summary(text)

    def test_contradictory_result_labels_are_rejected(self):
        for text in [
            'test result: ok. 1 passed; 1 failed; 0 ignored;',
            'test result: FAILED. 1 passed; 0 failed; 0 ignored;',
        ]:
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                test_summary(text)
