# Similar perfumes

"Something like Creed Aventus, up to 4,000 ₴?" Zoomer answers this with the `find_similar` tool. The tool ranks the catalog by arithmetic on vectors built from each product's notes, and the model only does what a language model is good at: it reads the question, picks the product and the filters, and explains the three results it gets back.

Handing the model a hundred candidate cards to rank would cost tens of thousands of input tokens per question, take a few seconds, and give a different order on every run. Between the model's two calls (the tool call and the answer), `find_similar` runs one Postgres query, three Qdrant requests and a formula in Python, and spends no tokens.

## The idea

Every product is one point in Qdrant with two vectors. Products that smell alike have vectors that point the same way, so "similar" means "nearest neighbour".

| Vector | What it captures | Shape |
|---|---|---|
| `accords` | the overall character: woody, smoky, fruity, sweet… | dense, one number from 0 to 1 per accord (26) |
| `notes` | the exact ingredients, rare ones counting most | sparse, one coordinate per note in the dictionary (90), almost all zero |

They see different things. Cedar and sandalwood are different notes, so their note vectors have nothing in common, but both are woody, so their accord vectors are close. Two fresh citrus perfumes have similar accords, but only the one with the same rare birch and pineapple shares Aventus's signature. The search ranks candidates by both:

```
score = 0.6 · accord similarity + 0.4 · note similarity
```

Both vectors are normalized to length 1, so each similarity is a dot product between 0 and 1 (the cosine of the angle between the vectors). The weights are a starting point.

## Product cards

Product headers carry the note pyramid as the brand lists it, and the product line flankers share:

```yaml
line: Aventus
notes:
  top: [Calabrian bergamot, Sicilian lemon, blackcurrant leaf]
  heart: [pineapple, pink pepper, jasmine]
  base: [birch, patchouli, musk]
```

A brand that names key notes instead of a pyramid (Le Labo, Tom Ford, Maison Francis Kurkdjian) gets a `key:` list. `RecordHeader` requires both fields on every product.

## The note dictionary

Brands spell the same note in many ways: `Calabrian bergamot` and `bergamot`, `ambrox` and `ambroxan`, `Madagascar vanilla` and `vanilla absolute`. Left as they are, they would be different coordinates, and a rare-looking spelling of a common note would get a large weight. `app/kb/notes.yaml` maps every spelling to one canonical note and lists the accords each note brings in:

```yaml
bergamot:
  aliases: [calabrian bergamot]
  accords: {citrus: 1.0, fresh: 0.5}
birch:
  accords: {smoky: 1.0, leather: 0.5, woody: 0.4}
```

`NoteDictionary.load()` (`app/kb/scent.py`) rejects an accord that isn't in the list and a spelling that belongs to two notes. Matching ignores case and extra spaces. `python -m app.kb.check_corpus` reports every note a product card uses that the dictionary doesn't know, so a new spelling gets reviewed before it can skew the weights. Ingest skips an unknown note with a warning.

Changing the accord list changes the size of the accord vector, so the products collection has to be deleted before the next ingest (`curl -X DELETE localhost:6333/collections/products`).

## Building the vectors

`build_vectors()` (`app/kb/scent.py`) turns every product's pyramid into its two vectors:

1. Each note gets a level weight: top 0.6, heart, base and key 1.0. Top notes fade within half an hour, the heart and the base carry the scent for hours. A note on two levels keeps the higher weight.
2. The note vector weighs each note by its level and by its IDF, `ln(products / products with this note)`. A note that every product has gets no weight.
3. The accord vector sums the accords of the product's notes, each times the note's level weight.
4. Both are normalized to length 1.

In the shipped catalog of 40 products:

| Note | Products with it | IDF |
|---|---|---|
| vanilla | 21 | 0.64 |
| bergamot | 15 | 0.98 |
| musk | 9 | 1.49 |
| pink pepper | 3 | 2.59 |
| pineapple, birch | 2 | 3.00 |

So Aventus's note vector is mostly pineapple and birch (0.52 each) and pink pepper (0.45), while its bergamot weighs 0.10. Its accord vector leads with fruity (0.53) and citrus (0.34).

## The products collection

Ingest (`python -m app.kb.ingest`) rebuilds the `products` collection (`QDRANT_PRODUCTS_COLLECTION`) on every run. IDF depends on the whole catalog, so one new product changes every note vector a little. The vectors come from the headers alone, so this calls no API. `app/kb/products.py` stores one point per product, with the record's number as its id:

```
id: 28
vectors:
  accords: [0.34, 0.53, 0.07, …]                      (26 numbers: citrus, fruity, green, …)
  notes:   {indices: [67, 10, 68, …], values: [0.52, 0.52, 0.45, …]}   (pineapple, birch, pink pepper, …)
payload: {record_id: KB-028, title: Creed Aventus, brand: Creed, line: Aventus, gender: men,
          concentration: EDP, availability: in_stock, price: 12490}
```

The payload holds what the search filters on and what the tool returns; the full card stays in `kb_records`. `gender`, `price` and `availability` have payload indexes.

## The search

```
find_similar(product="Creed Aventus", k=3, max_price=4000, gender="men")
 1. product → kb_records: a record id as it is, or the product title with the best
    pg_trgm word similarity (at least 0.7)                     ── Postgres
 2. the reference point's two vectors                          ── Qdrant
 3. in parallel: 30 neighbours by accords, 30 by notes          ── Qdrant
    filter: price ≤ max_price, gender (+ unisex), not discontinued, not the product itself
 4. both similarities for every candidate, score, sort,
    at most one product per line, the best k                   ── Python
 5. envelope: the reference, and for each match its card fields, the scores,
    the shared notes and the shared accords
```

The name lookup uses `word_similarity()` from the `pg_trgm` extension (migration `0010`), so a part of the title ("aventus", "Club de Nuit") finds the card. The threshold is 0.7: names of perfumes we don't sell that share words with ours, like "Chanel No 5" or "Invictus Victory", score up to 0.6 and get `NOT_FOUND` instead of a wrong card. "EDP" doesn't match "Eau de Parfum", so the tool asks for the concentration spelled out. The prompt asks the model for the name in English, as the shop writes it, so Aventus written in Ukrainian letters arrives as "Creed Aventus". A name that fits several cards equally well, as "Sauvage" fits all three Sauvage cards, gets the one with the lowest record id. The result names the reference it used, so the model can see which card it got.

The line rule keeps three flankers of one perfume from filling the answer: for Sauvage Eau de Toilette, the Eau de Parfum makes it in and the Elixir doesn't.

| Argument | |
|---|---|
| `product` | the product's name in English, e.g. `Creed Aventus`, or its record id, `KB-028` |
| `k` | 1–5, default 3 |
| `max_price` | UAH or null; compares with the cheapest bottle |
| `gender` | `men`, `women` or null; unisex perfumes always stay in |

A name with no product card returns `NOT_FOUND`, and the prompt tells the model to say we don't sell that perfume and search the knowledge base for its style instead. The step's record ids are the reference and the matches, so the answer can cite every card, and the read/write separation of the hardened mode counts the call as a read.

Some results on the shipped catalog, without filters:

| Product | Top match | Accords | Notes | Shared notes |
|---|---|---|---|---|
| Creed Aventus | Armaf Club de Nuit Intense Man | 0.88 | 0.68 | birch, pineapple, musk |
| Dior Sauvage Eau de Toilette | Dior Sauvage Eau de Parfum | 0.63 | 0.66 | pepper, ambroxan, bergamot |
| YSL Black Opium | Lancôme La Vie Est Belle | 0.86 | 0.31 | orange blossom, pear, patchouli |
| Molecule 01 | Mugler Alien | 0.67 | 0 | none: the accords carry it |

## At catalog scale

The design holds for a catalog of 10,000 products in Postgres:

- The vectors are small (26 floats and a handful of notes), so the collection stays tiny. Qdrant builds the HNSW graph once a segment passes its indexing threshold, and the payload indexes keep the filtered search fast.
- The name lookup scans the product titles. With many thousands of rows, a GIN trigram index on `title` and the `<%` operator let Postgres use an index for it.
- The neighbours could also be precomputed every night into a table (`product_id, similar_id, score`). That makes a lookup trivial, but the filters then run after the fact: with a 2,000 ₴ budget, none of the 50 stored neighbours may fit. The online query filters inside the search.
- With purchase or wishlist data, collaborative filtering ("customers who liked Aventus also bought…") would find similarities the notes don't show. The note vectors stay as the fallback for new products that have no history yet.
