"""Execute the firmware's C contract parser on the host, without ESP-IDF."""

import ctypes
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("cc")
        if compiler is None:
            raise RuntimeError("A C compiler is required for contract regression tests")
        cls.temp = tempfile.TemporaryDirectory(prefix="ticmeter-contracts-")
        cls.addClassCleanup(cls.temp.cleanup)
        library = Path(cls.temp.name) / "contracts.so"
        subprocess.run(
            [compiler, "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "main/include"), str(ROOT / "main/linky_contract.c"),
             "-o", str(library)],
            check=True, capture_output=True, text=True,
        )
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.linky_contract_detect.argtypes = [ctypes.c_bool, ctypes.c_char_p, ctypes.c_char_p]
        cls.lib.linky_contract_detect.restype = ctypes.c_int
        header = (ROOT / "main/include/linky_contract.h").read_text()
        cls.ids = {name: index for index, name in enumerate(re.findall(r"^\s+(C_\w+),", header, re.M))}

    def detect(self, name, tariff="", historical=False):
        return self.lib.linky_contract_detect(
            historical,
            name.encode() if name is not None else None,
            tariff.encode() if tariff is not None else None,
        )

    def check_cases(self, cases, historical=False):
        for name, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(self.detect(name, historical=historical), self.ids[expected])

    def test_zen_estival_from_reported_frame(self):
        self.assertEqual(self.detect("HSC ETE HIVER   ", "HSC Hiver       "), self.ids["C_ZEN_ESTIVAL"])

    def test_estival_is_distinct_from_nonseasonal_super_off_peak(self):
        self.check_cases([("HSC ETE HIVER", "C_ZEN_ESTIVAL"), ("H SUPER CREUSES", "C_HEURES_SUPER_CREUSES")])

    def test_existing_standard_contracts(self):
        self.check_cases([
            ("BASE", "C_BASE"), ("H PLEINE/CREUSE", "C_HC"),
            ("EJP", "C_EJP"), ("TEMPO", "C_TEMPO"), ("ZEN FLEX", "C_ZEN_FLEX"),
            ("SEM WE LUNDI", "C_SEM_WE_LUNDI"), ("SEM WE MERCREDI", "C_SEM_WE_MERCREDI"),
            ("SEM WE VENDREDI", "C_SEM_WE_VENDREDI"), ("HC et Week-End", "C_HC_WE"),
        ])

    def test_flex_pointe_mobile_calendar(self):
        self.assertEqual(self.detect("Pointe Mobile   ", "HC Jnormal"), self.ids["C_ZEN_FLEX"])

    def test_weekend_calendars_remain_distinct(self):
        self.check_cases([
            ("SEM WE", "C_SEM_WE"), ("HC SEM ET HC WE ", "C_HC_SEM_WE"),
            ("HC SEM WE LUNDI ", "C_HC_SEM_WE_LUNDI"),
            ("HC SEM WE MERCR ", "C_HC_SEM_WE_MERCREDI"),
            ("HC SEM WE VENDR ", "C_HC_SEM_WE_VENDREDI"),
        ])

    def test_padding_case_and_repeated_spaces(self):
        self.check_cases([
            ("  hsc  ete hiver ", "C_ZEN_ESTIVAL"),
            ("   hc ET week-end", "C_HC_WE"), ("\tH PLEINE/CREUSE ", "C_HC"),
            ("     tempo      ", "C_TEMPO"),
        ])

    def test_historical_contracts(self):
        self.check_cases([
            ("BASE", "C_BASE"), ("HC..", "C_HC"), ("EJP.", "C_EJP"),
            ("BBR", "C_TEMPO"), ("BBRA", "C_TEMPO"), ("BBRB", "C_TEMPO"),
            ("BBRC", "C_TEMPO"), ("BBRX", "C_TEMPO"), ("BBRY", "C_TEMPO"), ("BBRZ", "C_TEMPO"),
            ("BBR(", "C_TEMPO"), ("BBR)", "C_TEMPO"), ("BBR*", "C_TEMPO"), ("BBR0", "C_TEMPO"),
        ], historical=True)

    def test_modes_do_not_share_contract_code_lists(self):
        for name in ("HSC ETE HIVER", "Pointe Mobile", "SEM WE", "TEMPO"):
            with self.subTest(name=name):
                self.assertEqual(self.detect(name, historical=True), self.ids["C_UNKNOWN"])
        self.assertEqual(self.detect("BBRX"), self.ids["C_UNKNOWN"])

    def test_missing_calendar_tempo_fallback(self):
        for tariff in ("HC BLEU", "HP BLEU", "HC BLANC", "HP BLANC", "HC ROUGE", "HP ROUGE", "HP ROUG"):
            with self.subTest(tariff=tariff):
                self.assertEqual(self.detect("                ", tariff), self.ids["C_TEMPO"])

    def test_unknown_calendar_is_not_overridden_by_tempo_color(self):
        self.assertEqual(self.detect("CUSTOM OFFER", "HC BLEU"), self.ids["C_UNKNOWN"])
        self.assertEqual(self.detect("HSC ETE HIVER", "HP BLEU"), self.ids["C_ZEN_ESTIVAL"])

    def test_partial_and_unrelated_names_are_not_matches(self):
        for name in ("B", "BA", "H", "HC", "SEM WE MER", "HSC ETE", "XBASE", "BASE EXTRA", "ANY", "NOT TEMPO", "BBRXX"):
            with self.subTest(name=name):
                self.assertEqual(self.detect(name), self.ids["C_UNKNOWN"])

    def test_corrupt_and_overlong_names_are_rejected(self):
        for name in ("BA\x01SE", "TEM\x7fPO", "TEM\x80PO", "HSC ETE HIVER" + "X" * 40):
            with self.subTest(name=name):
                self.assertEqual(self.detect(name, "HC BLEU"), self.ids["C_UNKNOWN"])

    def test_null_and_ambiguous_missing_data(self):
        self.assertEqual(self.detect(None, None), self.ids["C_UNKNOWN"])
        for tariff in ("BASE", "HC Hiver", "HSC Hiver", "BLEU", "BLUEBERRY", "HC Jnormal"):
            with self.subTest(tariff=tariff):
                self.assertEqual(self.detect("", tariff), self.ids["C_UNKNOWN"])

    def test_contract_tables_are_complete_and_tuya_has_only_final_sentinel(self):
        count = self.ids["C_COUNT"]
        standard = (ctypes.c_char_p * count).in_dll(self.lib, "linky_std_str_contract")
        tuya = (ctypes.c_char_p * (count + 1)).in_dll(self.lib, "linky_tuya_str_contract")
        for contract in range(self.ids["C_BASE"], count):
            with self.subTest(contract=contract):
                self.assertTrue(standard[contract])
                self.assertEqual(self.detect(standard[contract].decode()), contract)
        self.assertTrue(all(tuya[index] for index in range(count)))
        self.assertIsNone(tuya[count])
        self.assertEqual(tuya[self.ids["C_ZEN_ESTIVAL"]], b"INCONNU")

    def test_existing_numeric_ids_are_stable(self):
        self.assertEqual(self.ids["C_HC_WE"], 11)
        self.assertEqual(self.ids["C_ZEN_ESTIVAL"], 12)


if __name__ == "__main__":
    unittest.main()
