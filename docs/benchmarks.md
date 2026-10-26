# Benchmarks

Both commands wipe the database they run against, so they refuse to run unless its name contains `test`, `eval` or `bench`.

## Search quality

```sh
createdb smriti_eval
export SMRITI_DATABASE_URL=postgresql+asyncpg://localhost/smriti_eval
smriti migrate
smriti eval --load --out report.json   # loads evals/seed, runs the workflow, scores the queries
smriti eval                             # re-score without reloading
```

A dataset is a directory with `corpus.jsonl` (`key`, `text` or `url` + `html`, optional `title`, `note`, `age_days`) and `queries.jsonl` (`q`, `targets`: corpus keys, `kind`). The report has recall@10, MRR and p50/p95 latency overall and per query kind, plus every miss with the top 5 results.

`evals/seed` has 36 items and 70 queries written by hand: keyword, paraphrase, vague, note and filter queries. CI fails if recall@10 drops below 0.95 or MRR below 0.75. It is a regression guard, not the 200 real queries the spec asks for; those come from personal use and should not be committed if they contain private data.

Latest run (bge-small-en-v1.5):

| Kind | Queries | recall@10 | MRR |
| --- | --- | --- | --- |
| all | 70 | 1.00 | 0.83 |
| keyword | 36 | 1.00 | 0.90 |
| paraphrase | 25 | 1.00 | 0.66 |
| vague | 3 | 1.00 | 1.00 |
| note | 3 | 1.00 | 1.00 |
| filter | 3 | 1.00 | 1.00 |

## Latency

```sh
createdb smriti_bench
export SMRITI_DATABASE_URL=postgresql+asyncpg://localhost/smriti_bench SMRITI_EMBED_PROVIDER=hash
smriti migrate
smriti bench --items 50000 --queries 300 --seed-db
```

`--seed-db` bulk-inserts synthetic items with Zipf-distributed vocabulary, so some terms match most of the library, which is the worst case for keyword ranking. Vectors come from the hash embedder so seeding takes minutes, not hours; the numbers cover retrieval, fusion and loading results, not the query embedding.

4 vCPU cloud container, Postgres 16, pgvector 0.6:

| Items | p50 | p95 |
| --- | --- | --- |
| 50,000 | 56 ms | 85 ms |

A bge-small query embedding adds about 4 ms on the same machine.

## Not yet measured

- pgvector HNSW against the custom index from project #5. The `VectorIndex` protocol in `search/retrievers.py` is where it plugs in.
- Extraction accuracy per type on 20+ real samples each.
- Enrichment cost per item with an LLM; the status page records it per step once an LLM is configured.
