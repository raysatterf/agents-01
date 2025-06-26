class DummyEnvironment:
    """A simple environment that provides static observations."""

    def __init__(self):
        self.observations = ["event1", "event2", "event3"]

    def run(self, agent):
        for obs in self.observations:
            agent.observe(obs)
        agent.run(["say_hello"])
