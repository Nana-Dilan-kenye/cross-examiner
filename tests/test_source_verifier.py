import unittest
from unittest.mock import patch

from src.source_verifier import verify_pdf_source


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdfReader:
    def __init__(self, _stream):
        self.pages = [
            FakePage(
                "Cameroon - RCV1\n"
                "MCV1 is discussed in the explanatory notes.\n"
                "2010 2011 2012 2013 2014 2015 "
                "2016 2017 2018 2019 2020 2021\n"
                "Estimate 50 51 52 53 54 55 56 57 58 59 60 61\n"
                "Administrative 60 61 62 63 64 65 66 67 68 69 70 71"
            )
        ]


class SourceVerifierTests(unittest.TestCase):
    @patch("src.source_verifier.urlopen")
    @patch("src.source_verifier.PdfReader", FakePdfReader)
    def test_rejects_other_antigen_heading_even_if_text_mentions_mcv1(
        self, mock_urlopen
    ):
        class FakeResponse:
            headers = {"Content-Type": "application/pdf"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, _size):
                return b"%PDF-fake"

        mock_urlopen.return_value = FakeResponse()

        finding = {
            "country": "Cameroon",
            "antigen": "MCV1",
            "year": "2020",
            "measure_a": "WUENIC estimate",
            "value_a": 60,
            "measure_b": "Administrative coverage",
            "value_b": 70,
        }

        result = verify_pdf_source("https://example.com/fake.pdf", finding)

        self.assertEqual(result["status"], "TABLE_NOT_FOUND")
        self.assertFalse(result["table_context_found"])


if __name__ == "__main__":
    unittest.main()
