"""Classifier exports."""

from omniscrape.classifier.detector import PageClassifier
from omniscrape.classifier.strategies import EscalationStrategy

__all__ = [
    "PageClassifier",
    "EscalationStrategy",
]
