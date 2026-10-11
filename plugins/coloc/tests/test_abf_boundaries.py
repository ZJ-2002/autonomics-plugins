import unittest

import test_abf_contract as common


class AbfBoundaryTests(unittest.TestCase):
    setUpClass = classmethod(common.AbfContractTests.setUpClass.__func__)
    run_case = common.AbfContractTests.run_case

    def test_frozen_p12_sensitivity_1e6(self):
        self.run_case(lambda columns,records,settings: settings.update(p12=1e-6))

    def test_frozen_p12_sensitivity_1e4(self):
        self.run_case(lambda columns,records,settings: settings.update(p12=1e-4))

    def test_single_variant_author_H3_zero(self):
        self.run_case(lambda columns,records,settings: records.__delitem__(slice(1,None)))

    def test_author_frequency_above_half(self):
        def change(columns,records,settings):
            settings['dataset1_maf'] = 'maf1'
            for record in records:
                record[3] = '0.7'
        self.run_case(change)

    def test_zero_pvalue(self):
        def change(columns,records,settings):
            common.AbfContractTests.pvalue_settings(columns,records,settings)
            records[0][4] = '0'
        self.run_case(change,refusal='pvalues must be in')

    def test_numeric_NA_is_not_lexical_identifier(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(1,'NA'),refusal='finite numbers')

    def test_negative_variance(self):
        self.run_case(lambda columns,records,settings: records[0].__setitem__(2,'-0.01'),refusal='varbeta must be positive')

    def test_mapping_alias(self):
        self.run_case(lambda columns,records,settings: settings.update(dataset1_beta='snp1'),refusal='must not alias')

    def test_ragged_row(self):
        self.run_case(lambda columns,records,settings: records[0].pop(),refusal='TSV rows must be nonempty and rectangular')

    def test_no_common_variants(self):
        def change(columns,records,settings):
            for record in records:
                record[5] = 'other_'+record[5]
        self.run_case(change,refusal='common snps can be identified')


if __name__=='__main__':
    unittest.main()
