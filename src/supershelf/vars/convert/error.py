"""A string that cannot be turned into a canonical spelling."""


class ConvertError(Exception):
    """The text cannot be converted. The message names the original value."""
