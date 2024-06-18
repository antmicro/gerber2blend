"""Class representing a single module of the pipeline."""

import logging

logger = logging.getLogger(__name__)


class Module:
    """Represents a single module of the pipeline, for example: board."""

    def execute(self) -> None:
        """Execute the current module.

        Errors during execution can be returned by raising an exception.
        """
