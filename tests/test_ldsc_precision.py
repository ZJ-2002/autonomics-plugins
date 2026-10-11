"""Required complete-precision metadata/missingness guards; no method grant."""
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location("ldsc_precision_contract_tests",Path(__file__).resolve().parents[1]/"plugins/ldsc-precision/tests/test_precision_contract.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
PrecisionContractTests=module.PrecisionContractTests
