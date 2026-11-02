"""A module that tries to register the built-in file name."""

from supershelf.output import OutputDriver


class Again(OutputDriver):
    """Same name as the built-in file driver."""

    name = "file"

    def check(self, spec):
        return None

    def prepare(self, spec, profile):
        return None

    def plan(self, prepared, context):
        return None

    def apply(self, action, dry_run=False):
        return None


DRIVERS = [Again]
