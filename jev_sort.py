"""An intentionally underspecified semantic comparator, with finite-list checks."""

import argparse
import csv
from dataclasses import asdict, dataclass
from functools import cmp_to_key
import json
from typing import Any, Callable, Iterable, TypeVar

from typesafe_sdk import Choice, TypeSafeClient

T = TypeVar("T")


class InconsistentComparison(ValueError):
    """The observed comparisons do not define a total preorder."""


@dataclass
class Judgment:
    left: Any
    right: Any
    choice: str
    probabilities: dict[str, float]
    confidence: float
    model: str


class JevComparator:
    def __init__(self, client: TypeSafeClient, model: str = "jev-latest"):
        self.client = client
        self.model = model
        self.judgments: list[Judgment] = []

    def __call__(self, left: Any, right: Any) -> int:
        response = self.client.system_one(
            model=self.model,
            state={"A": left, "B": right},
            questions={
                "comparison": Choice(
                    instructions="Which comes first?",
                    criteria={
                        "A": "A comes first.",
                        "B": "B comes first.",
                        "tie": "Neither comes first; they are equal in order.",
                    },
                )
            },
        )
        answer = response.choices["comparison"]
        self.judgments.append(Judgment(
            left, right, answer.choice, dict(answer.probabilities),
            answer.confidence, response.model,
        ))
        return {"A": -1, "B": 1, "tie": 0}[answer.choice]

    def sort(self, items: Iterable[T], batch_size: int = 100) -> list[T]:
        """Batch semantic comparisons; exact JSON equality is a tie by definition."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        values = list(items)
        keys = [json.dumps(v, sort_keys=True, allow_nan=False) for v in values]
        relation = [[0 for _ in values] for _ in values]
        pairs = [(i, j) for i in range(len(values)) for j in range(len(values))
                 if keys[i] != keys[j]]
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start:start + batch_size]
            questions = {
                f"pair_{i}_{j}": Choice(
                    instructions={"question": "Which comes first?",
                                  "A": values[i], "B": values[j]},
                    criteria={"A": "A comes first.", "B": "B comes first.",
                              "tie": "Neither comes first; they are equal in order."},
                ) for i, j in batch
            }
            response = self.client.system_one(model=self.model, state={}, questions=questions)
            for i, j in batch:
                answer = response.choices[f"pair_{i}_{j}"]
                self.judgments.append(Judgment(
                    values[i], values[j], answer.choice, dict(answer.probabilities),
                    answer.confidence, response.model,
                ))
                relation[i][j] = {"A": -1, "B": 1, "tie": 0}[answer.choice]
        indices = checked_sort(range(len(values)), lambda i, j: relation[i][j])
        return [values[i] for i in indices]


def checked_sort(items: Iterable[T], compare: Callable[[T, T], int]) -> list[T]:
    """Check all ordered pairs, then stably sort original objects.

    Calls the comparator n² times, including self and reversed comparisons.
    Freezes those observations for this sort; does not promise future model
    calls agree. Validation takes O(n³) time and O(n²) space.
    """
    values = list(items)
    n = len(values)
    relation = [[compare(a, b) for b in values] for a in values]
    for i in range(n):
        for j in range(n):
            if relation[i][j] not in (-1, 0, 1):
                raise ValueError("Comparator must return -1, 0, or 1")
            if i == j and relation[i][j] != 0:
                raise InconsistentComparison(f"Self-comparison is not a tie at index {i}")
            if relation[i][j] != -relation[j][i]:
                raise InconsistentComparison(f"Reversal disagrees at indices {i}, {j}")
    # Transitivity of <= also checks that ties form consistent equivalence classes.
    for i in range(n):
        for j in range(n):
            for k in range(n):
                if relation[i][j] <= 0 and relation[j][k] <= 0 and relation[i][k] > 0:
                    raise InconsistentComparison(
                        f"Transitivity fails at indices {i}, {j}, {k}"
                    )
    indices = sorted(range(n), key=cmp_to_key(lambda i, j: relation[i][j]))
    return [values[i] for i in indices]


def jev_sort(items: Iterable[T], *, client: TypeSafeClient,
             model: str = "jev-latest") -> list[T]:
    return JevComparator(client, model).sort(items)


def main() -> None:
    from dotenv import load_dotenv

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("items", help='Comma-separated text, e.g. "one,2,3"')
    parser.add_argument("--json", action="store_true", help="Read a JSON list instead of comma-separated text")
    parser.add_argument("--model", default="jev-latest")
    parser.add_argument("--trace", action="store_true", help="Include raw model judgments")
    parser.add_argument("--batch-size", type=int, default=100, help="Comparisons per request (default: 100)")
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")
    try:
        if args.json:
            items = json.loads(args.items)
            if not isinstance(items, list):
                raise ValueError("Expected a JSON list")
            json.dumps(items, allow_nan=False)
        else:
            rows = list(csv.reader([args.items], skipinitialspace=True, strict=True))
            items = [item.strip() for item in rows[0]] if rows else []
    except (ValueError, csv.Error) as exc:
        parser.error(str(exc))
    load_dotenv()
    with TypeSafeClient() as client:
        comparator = JevComparator(client, args.model)
        try:
            result = {"sorted": comparator.sort(items, batch_size=args.batch_size)}
        except InconsistentComparison as exc:
            result = {"error": str(exc)}
        if args.trace:
            result["judgments"] = [asdict(j) for j in comparator.judgments]
        output = result if args.trace or "error" in result else result["sorted"]
        print(json.dumps(output, indent=2, ensure_ascii=False))
        if "error" in result:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
