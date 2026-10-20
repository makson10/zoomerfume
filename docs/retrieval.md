# Retrieval

How the knowledge base gets from Markdown files into Qdrant, how search works, and how we check that a search by meaning finds the right record.

## The corpus

`backend/corpus/` holds 96 records, one Markdown file each (`KB-001.md` … `KB-096.md`): 40 product cards, 18 policies, 8 company pages, 20 FAQ answers and 10 news posts, about 45,000 words. Every file starts with a YAML header, followed by a Markdown body split into `##` sections.

```yaml
---
id: KB-028
title: Creed Aventus
type: product              # product | policy | company | faq | news
updated: 2026-10-01
brand: Creed               # the fields below are for products only
concentration: EDP
family: chypre fruity
gender: men
seasons: [spring, summer, autumn]
sizes:
  - {ml: 50, price: 12490, points: 624}
  - {ml: 100, price: 17890, points: 894}
decant: {ml: 10, price: 2490, points: 124}
availability: in_stock     # in_stock | few_left | pre_order | discontinued
---
```

`app/kb/corpus.py` parses the files with a pydantic model (`RecordHeader`), so a broken header fails loudly. `python -m app.kb.check_corpus` checks the records against each other: points match the price, every `KB-…` link exists, a price quoted next to a product link is one of that product's prices, contacts use the reserved `.example` domain, and no record ID appears in square brackets, which is the citation format Zoomer will use. A unit test runs the same checks on the shipped corpus.

Records link to each other as plain IDs ("see KB-052"). Zoomer cites as `[KB-052]`, so a bracketed ID inside a record could be copied into an answer without that record ever being retrieved.

## Chunking

`app/kb/chunking.py` turns a record into chunks of at most 500 tokens, counted with `cl100k_base`, the tokenizer of the embedding model.

1. The body is split at `##` headings. A section is the natural unit: "Notes", "How it wears", "Refunds".
2. Neighbouring sections are packed into one chunk while they fit. A product card usually becomes two chunks: overview, notes and wear, then Zoomer's take, prices and similar perfumes.
3. A section too big for a chunk is split on paragraphs, then sentences, and only as a last resort on token windows.
4. Every chunk after the first starts with the last ~75 tokens (about 15%) of the chunk before it, cut at a line, sentence or word boundary. A fact near a boundary can then be found from either side.
5. Each chunk gets a breadcrumb such as `Creed Aventus › Notes, How it wears`. The breadcrumb is embedded together with the chunk text, so a chunk deep in a record still carries the record's subject.

The result is deterministic: the same file always gives the same chunks. The full corpus gives 206 chunks, 78–494 tokens each (median 370), 77,554 tokens to embed. With `text-embedding-3-small` at $0.02 per million tokens, a full ingest costs about $0.0016.

We tried packing less. With the same 500-token limit, sections were only merged while the chunk stayed under a smaller budget:

| Packing budget | Chunks | hit@1 | hit@5 |
|---|---|---|---|
| up to ~500 tokens (current) | 206 | 15/20 | 19/20 |
| up to 250 tokens | 367 | 14/20 | 17/20 |
| up to 150 tokens | 587 | 16/20 | 18/20 |

Smaller chunks didn't help: they found the right record first slightly more often, but more often lost it altogether, and they tripled the number of points. Whole sections packed up to the limit keep enough context in each chunk.

## Embeddings and Qdrant

`app/kb/embeddings.py` embeds the chunks with `text-embedding-3-small` (1536 dimensions), in batches of up to 100 texts per request. Transient API errors are retried by the OpenAI client (`OPENAI_MAX_RETRIES`).

`app/kb/store.py` keeps the vectors in the Qdrant collection `kb_chunks`:

- Cosine distance, 1536 dimensions.
- Point id = `uuid5(record id + chunk index)`, so a re-run overwrites the same points instead of adding copies. When a record gets shorter, its chunks beyond the new count are deleted.
- Payload: `source` (file name), `title`, `chunk_index`, `record_id`, `type`, `updated`, `section` (the breadcrumb), `text`, and `price` for products: the price of the cheapest bottle. Payload indexes on `record_id` and `type` (keyword) and `price` (integer) keep filtered searches fast.

### The HNSW index

The collection has an explicit HNSW config: `m=16` links per node and `ef_construct=100` candidates while building the graph. That alone isn't enough. Qdrant builds the graph only for segments with more vector data than `indexing_threshold` (in kilobytes) and searches smaller segments by brute force. The server default in Qdrant 1.19 is 10,000 kB, while our whole corpus is about 1,200 kB (one 1536-dimension vector is about 6 kB). So we set `indexing_threshold=10`.

The proof is `indexed_vectors_count` in the collection info. We loaded the same 206 vectors into two collections:

| Collection config | Points | Indexed vectors |
|---|---|---|
| Qdrant defaults (threshold 10,000 kB) | 206 | 0 |
| `kb_chunks` (threshold 10 kB) | 206 | 206 |

```bash
curl -s localhost:6333/collections/kb_chunks | jq '.result | {status, points_count, indexed_vectors_count}'
```

The ingest command waits until Qdrant has finished building the index and prints both numbers. On a fresh collection the two numbers are equal. After any re-embed or delete (`--force`, a changed or removed record), `indexed_vectors_count` is higher than `points_count` and stays that way: replaced and deleted vectors remain in the index, and Qdrant vacuums only segments with at least 1,000 vectors (`vacuum_min_vector_number`), more than this whole collection. A `--force` run gives 206 points and 285 indexed vectors, for example. Search is not affected, because deleted vectors are never returned.

A filtered search that leaves only a few points, for example only products under 3,000 ₴, may be answered by checking those points exactly instead of walking the graph. Qdrant's query planner decides this, and for a corpus this small it's the faster path.

## Loading: `python -m app.kb.ingest`

1. Parse every record and read the content hashes stored in the `kb_records` table.
2. Create the collection and its payload indexes if they don't exist. A new, empty collection makes this a full run.
3. Skip records whose file hash hasn't changed. Chunk and embed the new and changed ones, upsert their points, and save the full record to `kb_records`.
4. Delete the points and rows of records that are no longer in the corpus.
5. Wait for the index and print a summary.

A second run right after the first embeds nothing:

```
Records: 96 total, 96 changed, 0 skipped, 0 deleted
Chunks: 206 embedded, 77,554 tokens
Qdrant kb_chunks: 206 points, 206 indexed vectors (HNSW)

Records: 96 total, 0 changed, 96 skipped, 0 deleted
Chunks: 0 embedded, 0 tokens
Qdrant kb_chunks: 206 points, 206 indexed vectors (HNSW)
```

`--force` re-embeds everything, which is needed after a change to the chunking or the embedding model. `--dry-run` shows what would change without calling OpenAI or writing anything.

`kb_records` keeps each record's header, body and hash, so a full record can be looked up by id without going through Qdrant.

## Search

`search(query, k, record_type, max_price)` in `app/kb/search.py` embeds the query and returns the `k` closest chunks, best first, with their record id, title, section, score and text. `record_type` limits the results to one record type. `max_price` keeps only products whose cheapest bottle costs at most that much; other records have no price, so it also limits the results to products.

```bash
python -m app.kb.search "vanilla and tobacco" --type product --max-price 3000 -k 3
1. 0.476  KB-026  Maison Margiela Replica Jazz Club › Zoomer's take, Sizes and prices, Similar in our shop · from 2,490 ₴
2. 0.438  KB-026  Maison Margiela Replica Jazz Club › Overview, Notes, How it wears, Who it's for · from 2,490 ₴
3. 0.393  KB-025  Maison Margiela Replica By the Fireplace › Who it's for, Zoomer's take, Sizes and prices, Similar in our shop · from 2,990 ₴
```

## The rephrase check

A search that only matches words isn't enough: customers rarely use the words a record uses. `backend/eval/rephrase.yaml` holds 20 questions written to avoid the key words of the record that answers them ("can my sister in Warsaw get an order?" for the international shipping policy, which lists Poland but never mentions Warsaw). `expected` lists every record that fully answers the question: the target first, then any FAQ or policy that covers the same rule. The list was fixed before the first run.

`python -m app.kb.eval_rephrase` searches each question (`k=5` chunks) and reports the rank of the first expected record among the records found. Target: hit@5 of at least 90%.

| # | Question | Expected | Rank | Top hit |
|---|---|---|---|---|
| 1 | how long can my package sit at the post office before it goes back? | KB-075, KB-042 | 1 | KB-075 (0.44) |
| 2 | how do I know I'm not getting a knockoff? | KB-051, KB-067, KB-061 | 1 | KB-067 (0.46) |
| 3 | can I try a tiny bit before committing to a whole bottle? | KB-052, KB-069 | 1 | KB-069 (0.48) |
| 4 | will you make it look pretty for a birthday present? | KB-053, KB-080 | 2 | KB-094 (0.30) |
| 5 | can I hand the money over at the door for a really expensive order? | KB-046, KB-079 | 1 | KB-046 (0.42) |
| 6 | if I buy late in the afternoon, does it still go out today? | KB-041 | miss | KB-074 (0.36) |
| 7 | I'm in the capital and need it tonight, possible? | KB-043, KB-091 | 1 | KB-091 (0.30) |
| 8 | can my sister in Warsaw get an order? | KB-045, KB-081 | 3 | KB-041 (0.34) |
| 9 | can I spread the cost over a few months? | KB-047, KB-078 | 1 | KB-078 (0.51) |
| 10 | do people who spend a lot get better perks? | KB-056 | 1 | KB-056 (0.34) |
| 11 | what's the most bonus I can knock off my bill? | KB-055, KB-076 | 2 | KB-084 (0.38) |
| 12 | the glass cracked on the way and it's leaking, help | KB-050, KB-071 | 1 | KB-071 (0.38) |
| 13 | do you use a lot of plastic when you mail stuff? | KB-066 | 1 | KB-066 (0.43) |
| 14 | if something isn't in stock yet, can I reserve it? | KB-054, KB-085 | 1 | KB-085 (0.48) |
| 15 | which city do my packages come from? | KB-062 | 1 | KB-062 (0.34) |
| 16 | something that smells like an old bar with a cigar and a drink? | KB-026 | 1 | KB-026 (0.43) |
| 17 | a scent like sitting next to burning logs in winter | KB-025 | 1 | KB-025 (0.51) |
| 18 | something that smells like a cold stream in the Alps | KB-029 | 1 | KB-029 (0.43) |
| 19 | which one smells a bit different on everyone, like your own skin but better? | KB-027 | 1 | KB-027 (0.48) |
| 20 | something light and happy for a teenage girl's first bottle | KB-020 | 3 | KB-038 (0.39) |

**hit@1: 15/20 (75%) · hit@5: 19/20 (95%).** The target is met.

What the misses and near-misses show:

- **#6, the miss.** "Late" pulls the search to "My parcel is late" (KB-074), and "go out today" sits closer to the Kyiv courier pages than to the dispatch rule in KB-041 ("orders paid by 15:00 Monday–Friday leave the warehouse the same day"). The warehouse page KB-062 also states the cut-off and comes 4th, but it wasn't in the expected list, and we don't change the list after a run. None of the smaller chunk sizes above fixed it either.
- **#4 and #11.** One word wins over the meaning: "birthday" pulls up the birthday sale news (KB-094), and "bonus" pulls up the gift card and points FAQ (KB-084). The right record is still second.
- **#20.** The top hit, Lattafa Yara, is a reasonable answer too: a soft, sweet scent at 1,290 ₴. Daisy comes third.
