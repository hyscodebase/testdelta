"""Run trusted project tests in a separate process (not a security sandbox)."""

from .supervisor import run_pytest

__all__ = ["run_pytest"]
