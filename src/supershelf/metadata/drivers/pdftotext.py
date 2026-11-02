"""pdftotext stdout. The only field is text, and it may be omitted."""

from __future__ import annotations

from supershelf.metadata.driver import DriverOptions, MetadataDriver, MetadataFile


class PdftotextDriver(MetadataDriver):
    """pdftotext stdout. The only field is text, and it may be omitted."""

    identity = "pdftotext"
    extensions = ("pdf",)
    mime_types = ("application/pdf",)
    single_field = "text"
    binary = "pdftotext"

    def extract(self, file: MetadataFile, field: str, options: DriverOptions) -> str:
        """Return stdout. The text field may be omitted."""
        return self.one_field(file, field, options, lambda: self._read(file, options))

    def _read(self, file: MetadataFile, options: DriverOptions) -> tuple[str, dict[str, str]]:
        timeout = options.run_timeout()
        stdout = options.runner.run(
            ["pdftotext", "-q", "-enc", "UTF-8", str(file.absolute), "-"],
            timeout,
        )
        text = stdout.strip()
        fields = {"text": text} if text else {}
        return stdout, fields

    def fields_from_payload(self, payload: str, options: DriverOptions) -> dict[str, str]:
        """The stored payload is stdout. The only field is text."""
        del options
        text = payload.strip()
        return {"text": text} if text else {}
