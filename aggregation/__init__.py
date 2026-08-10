from aggregation.base import AggregationStrategy, MeanAggregation
from aggregation.median import MedianAggregation
from aggregation.trimmed_mean import TrimmedMeanAggregation

_REGISTRY = {
    "mean": MeanAggregation,
    "median": MedianAggregation,
    "trimmed_mean": TrimmedMeanAggregation,
}


def get_aggregation(name: str, **kwargs) -> AggregationStrategy:
    if name not in _REGISTRY:
        raise ValueError(f"unknown aggregation: {name}")
    return _REGISTRY[name](**kwargs)
