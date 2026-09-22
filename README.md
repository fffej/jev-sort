# Jev sort

Jev is the comparator. Its entire question is **“Which comes first?”**
The state contains `A` and `B`; the answers are A, B, or tie. No numeric,
alphabetical, or other sorting criterion is supplied. Ambiguity is intentional.

```sh
uv sync
# Set TYPESAFE_API_KEY in your environment or .env.
uv run jev-sort 'one,2,3'
uv run jev-sort 'small, medium, large' --trace
uv run jev-sort '"Washington, DC",London,Paris'
uv run jev-sort --json '["one", 2, 3]' --trace
```

Comma-separated input stays as strings, with surrounding whitespace trimmed.
Quote fields containing commas using CSV double quotes. Empty fields and duplicates
are retained. The command prints a JSON list on success; `--trace` adds the raw
judgments. Use `--json` for typed JSON input. Contradictory comparisons still
produce an error instead of a sorted list.

```python
from typesafe_sdk import TypeSafeClient
from jev_sort import jev_sort

with TypeSafeClient() as client:
    result = jev_sort(["one", 2, 3], client=client)
```

Inputs sent to Jev must be JSON-compatible. Original Python objects are returned
without conversion or mutation; duplicates are retained and ties are stable.

Exact JSON-equal values tie in code (including self-comparisons). For other pairs,
we ask both orientations. We check self equality, reversal consistency, and transitivity
(including ties), then use Python's `sorted` with `cmp_to_key` over the frozen
comparison table. Inconsistent observations raise `InconsistentComparison`;
the CLI exits 1 and can include the judgments with `--trace`.

Comparisons are batched into requests of up to 100 questions (`--batch-size`).
Five distinct items need 20 questions in one request, instead of 25 requests.
Each question's structured instructions contain `question: "Which comes first?"`
and its own `A` and `B` values; shared state is `{}`. Question IDs only map
responses back to pairs. No sorting criterion is added.
This costs O(n²) model questions and O(n³) local validation, so start with small lists.
Checks establish consistency for this observed finite list, not semantic truth
or repeatability across runs. Low confidence is recorded, not treated as a tie.

Run offline tests: `uv run python -m unittest discover -s tests`.

Integration follows the [TypeSafe Python SDK](https://docs.typesafe.ai/sdk/python).
The [Choice documentation](https://docs.typesafe.ai/primitives/choice) describes
structured instructions, the response `answers` map, and parallel questions.
The SDK's `response.choices` is the Choice-only view of that map. We use `choice`
as the outcome, retaining `probabilities` and `confidence` in the trace.
