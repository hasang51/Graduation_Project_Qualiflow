"""Production-oriented, deterministic evaluation layer for QualiFlow gold-set metrics."""

from evaluation.metrics import FieldMatchResult, compare_values, run_field_evaluation
from evaluation.policy import EvaluationPolicy, load_evaluation_policy

__all__ = [
    "EvaluationPolicy",
    "FieldMatchResult",
    "compare_values",
    "load_evaluation_policy",
    "run_field_evaluation",
]
