"""Builtin metadata drivers. One module per backend."""

from supershelf.metadata.drivers.command import CommandDriver
from supershelf.metadata.drivers.exiftool import ExiftoolDriver
from supershelf.metadata.drivers.pdf import PdfDriver
from supershelf.metadata.drivers.pdftotext import PdftotextDriver

__all__ = [
    "CommandDriver",
    "ExiftoolDriver",
    "PdfDriver",
    "PdftotextDriver",
]
