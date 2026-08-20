from typing import Protocol

from src.job import Job


class JobSource(Protocol):
    def search(self, preferences: dict) -> list[Job]: ...
