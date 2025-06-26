from modules.memory import Memory
from modules.planner import Planner
from utils.logger import logger

class BasicAgent:
    """A minimal agent that observes, plans, and acts."""

    def __init__(self):
        self.memory = Memory()
        self.planner = Planner()

    def observe(self, observation: str):
        logger.info(f"Observed: {observation}")
        self.memory.add(observation)

    def act(self, goals):
        actions = self.planner.plan(goals)
        for action in actions:
            logger.info(f"Executing action: {action}")
            # Placeholder for action execution

    def run(self, goals):
        self.act(goals)
        logger.info(f"Memory: {self.memory.recall()}")
