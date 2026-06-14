from src.pdf_report import write_pdf_report


def test_write_pdf_report_creates_pdf_file(tmp_path) -> None:
    path = tmp_path / "forecast_report.pdf"

    result = write_pdf_report(
        "\n".join(
            [
                "FX BARRIER TOUCH INTELLIGENCE REPORT",
                "",
                "QUESTION",
                "Will AUD/USD touch the 0.7154 up barrier within 92 calendar days?",
                "",
                "PROBABILITY DISTRIBUTION",
                "Barrier touched before expiry: 77.67%",
                "Barrier not touched before expiry: 22.33%",
                "",
                "MODEL RISK NOTES",
                "- This is a probability estimate, not investment advice.",
            ]
        ),
        path,
    )

    assert result == path
    assert path.exists()
    assert path.read_bytes().startswith(b"%PDF")
