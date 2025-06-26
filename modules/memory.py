class Memory:
    """A simple episodic memory placeholder."""

    def __init__(self):
        self._episodes = []

    def add(self, event: str):
        self._episodes.append(event)

    def recall(self):
        return list(self._episodes)
