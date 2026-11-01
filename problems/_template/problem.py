"""Problem schema stub. Implement XInstance/XSolution + Instance/Solution aliases."""

from dataclasses import dataclass


@dataclass
class XInstance:
    # fields ...
    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> "XInstance":
        raise NotImplementedError


@dataclass
class XSolution:
    # fields ...
    def to_dict(self) -> dict:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, d: dict) -> "XSolution":
        raise NotImplementedError


Instance = XInstance
Solution = XSolution
