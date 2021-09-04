import collections


class PendingFix:
    """Allows a rewrite operation to span multiple lines.

    In the main rewrite loop, every time a helper function returns a
    ``PendingFix`` object instead of a string, this object will be called
    with the following line.
    """

    def __init__(self, line: bytes) -> None:
        """Analyse and store the first line."""
        self.accumulator = collections.deque([line])

    def __call__(self, line: bytes) -> object:
        """Process line considering the accumulator.

        Return self to keep processing the following lines or a string
        with the final result of all the lines processed at once.
        """
        raise NotImplementedError("Abstract method needs to be overwritten")


def get_line_ending(line: bytes) -> bytes:
    """
    Return line ending.

    Note: this function should be somewhere else.
    """
    non_whitespace_index = len(line.rstrip()) - len(line)
    if not non_whitespace_index:
        return b""
    else:
        return line[non_whitespace_index:]
