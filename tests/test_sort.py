import unittest
import json
from types import SimpleNamespace

import httpx2
from typesafe_sdk import TypeSafeClient

from jev_sort import InconsistentComparison, JevComparator, checked_sort


class SortTests(unittest.TestCase):
    def test_batched_wire_body_and_response_mapping(self):
        calls = []

        def handle(request):
            body = json.loads(request.content)
            calls.append(body)
            self.assertEqual(request.url.path, "/v1/systemone")
            self.assertEqual(body["state"], {})
            self.assertEqual(body["model"], "jev-latest")
            answers = {}
            for name, question in reversed(list(body["questions"].items())):
                self.assertEqual(question["type"], "choice")
                self.assertEqual(set(question["criteria"]), {"A", "B", "tie"})
                instructions = question["instructions"]
                self.assertEqual(instructions["question"], "Which comes first?")
                a, b = instructions["A"], instructions["B"]
                self.assertNotEqual(a, b)
                choice = "A" if a < b else "B"
                answers[name] = {"type": "choice", "choice": choice,
                                 "probabilities": {k: float(k == choice) for k in ("A", "B", "tie")},
                                 "confidence": 1.0}
            return httpx2.Response(200, json={"model": "test", "answers": answers,
                                             "usage": {"input_tokens": 10, "output_tokens": 10}})

        with TypeSafeClient(api_key="test", base_url="https://api.typesafe.ai",
                            transport=httpx2.MockTransport(handle)) as client:
            comparator = JevComparator(client)
            self.assertEqual(comparator.sort(["3", "1", "2", "1"], batch_size=4),
                             ["1", "1", "2", "3"])
            self.assertEqual([len(c["questions"]) for c in calls], [4, 4, 2])
            self.assertEqual(len(comparator.judgments), 10)
            calls.clear()
            self.assertEqual(comparator.sort([]), [])
            self.assertEqual(comparator.sort(["1", "1"]), ["1", "1"])
            self.assertEqual(calls, [])

    def test_numeric(self):
        self.assertEqual(checked_sort([3, 1, 2], lambda a, b: (a > b) - (a < b)), [1, 2, 3])

    def test_stable_original_objects(self):
        items = [{"key": 2}, {"key": 1}, {"key": 2}]
        result = checked_sort(items, lambda a, b: (a["key"] > b["key"]) - (a["key"] < b["key"]))
        for actual, expected in zip(result, [items[1], items[0], items[2]]):
            self.assertIs(actual, expected)
        self.assertEqual(len(items), 3)

    def test_empty(self):
        self.assertEqual(checked_sort([], lambda a, b: self.fail()), [])

    def test_self_and_reversal(self):
        for matrix in ([[1]], [[0, -1], [-1, 0]]):
            with self.assertRaises(InconsistentComparison):
                checked_sort(range(len(matrix)), lambda a, b: matrix[a][b])

    def test_cycle_and_inconsistent_ties(self):
        for matrix in ([[0, -1, 1], [1, 0, -1], [-1, 1, 0]],
                       [[0, 0, -1], [0, 0, 0], [1, 0, 0]]):
            with self.assertRaises(InconsistentComparison):
                checked_sort(range(3), lambda a, b: matrix[a][b])

    def test_prompt_and_types(self):
        class Client:
            def system_one(inner, **kwargs):
                self.assertEqual(kwargs["state"], {"A": "one", "B": 2})
                self.assertEqual(kwargs["questions"]["comparison"].instructions, "Which comes first?")
                return SimpleNamespace(model="test", choices={"comparison": SimpleNamespace(
                    choice="A", probabilities={"A": .8, "B": .1, "tie": .1}, confidence=.7)})
        comparator = JevComparator(Client())
        self.assertEqual(comparator("one", 2), -1)
        self.assertEqual(len(comparator.judgments), 1)


if __name__ == "__main__":
    unittest.main()
