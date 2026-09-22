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
