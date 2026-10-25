# Docker Compose: what it sets up for the stack

`docker compose up` turns `docker-compose.yml` into five containers, one network and two volumes. This page goes through each piece Compose creates for us: the network, the DNS names, the volumes, the startup order and the config. It also covers what survives a restart.

| Service | Image | What it runs | How long it runs |
|---|---|---|---|
| `postgres` | `postgres:17.11-alpine` | the database | until stopped (`restart: unless-stopped`) |
| `qdrant` | `qdrant/qdrant:v1.19.1` | the vector store | until stopped |
| `migrate` | `zoomerfume:<APP_VERSION>` | `alembic upgrade head` | once, then exits |
| `ingest` | `zoomerfume:<APP_VERSION>` | `python -m app.kb.ingest` | once, then exits |
| `api` | `zoomerfume:<APP_VERSION>` | uvicorn: the API and the web chat | until stopped |

Postgres and Qdrant are pinned to exact versions, so a pull next month gets the same databases. The app image is tagged with the app version (see [One image, three services](#one-image-three-services)).

## Network

Compose creates one bridge network per project, named after the folder: `zoomerfume_default`. Every service joins it, and each container gets an address from its subnet. On our machine (`docker network inspect zoomerfume_default`) the subnet was `172.21.0.0/16`, with Postgres at `172.21.0.2`, Qdrant at `172.21.0.3` and the API at `172.21.0.4`.

Containers on the network reach each other on any port. From the outside, only the published ports are reachable: `api` publishes 8000 on `127.0.0.1`, so the browser on this machine gets the web chat and nothing else on the local network does. Postgres and Qdrant publish no ports in `docker-compose.yml`. The dev override (`docker-compose.override.yml`) publishes 5432 and 6333, also on `127.0.0.1`, for `psql` and a backend run on the host.

## DNS: why `postgres:5432` resolves

Every container on the network sends DNS queries to Docker's embedded DNS server, `127.0.0.11`. It answers each service name with that container's address on the network:

```
$ docker compose exec api cat /etc/resolv.conf
nameserver 127.0.0.11
$ docker compose exec api getent hosts postgres qdrant
172.21.0.2      postgres
172.21.0.3      qdrant
```

So the app's settings name services, never addresses: `DB_HOST=postgres` and `QDRANT_URL=http://qdrant:6333`. An address can change when a container is recreated, but the name stays the same. A stopped container drops out of DNS. With Qdrant stopped, `/ready` answers 503 with `"qdrant": "unavailable"`, and the log says `Name or service not known`.

## Volumes

Two named volumes hold all the data:

- `zoomerfume_postgres_data`, mounted at `/var/lib/postgresql/data`: users, conversations, agent history, turns, notes, costs and the knowledge base records.
- `zoomerfume_qdrant_data`, mounted at `/qdrant/storage`: the knowledge base vectors.

Docker keeps a volume apart from the containers that use it. A restart, a rebuild or a recreated container finds the same data. The `api` container keeps nothing of its own: the session lives in a signed cookie, everything else in Postgres. Only `docker compose down -v` deletes the volumes.

## Config

The root `.env` feeds Compose in two ways:

- `env_file: .env` passes every variable into `migrate`, `ingest` and `api`. The app reads environment variables only.
- Compose also fills `${...}` in `docker-compose.yml` from `.env`. The `postgres` service gets `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` from `DB_USER`, `DB_PASSWORD` and `DB_NAME`. One set of variables configures both sides, so they always match.

The credentials have no defaults. Without `DB_PASSWORD`, Compose refuses to start anything:

```
$ docker compose up
error while interpolating services.postgres.environment.POSTGRES_PASSWORD:
required variable DB_PASSWORD is missing a value: set DB_PASSWORD in .env
```

The app refuses as well: the image started any other way without `DB_PASSWORD` stops at startup with a validation error for `db_password` ("Field required").

Postgres reads `POSTGRES_*` only when it starts on an empty data volume. To change the password of an existing database, run `ALTER USER` in `psql`, or start over with `docker compose down -v`.

## Startup order

Each long-running service has a health check: `pg_isready` for Postgres, an open port 6333 for Qdrant and `GET /health` for the API. `depends_on` turns them into an order:

```
postgres ── healthy ──► migrate ── exited 0 ──► ingest ── exited 0 ──► api
qdrant ──── healthy ────────────────────────────┘
```

`migrate` waits for a healthy Postgres. `ingest` waits for `migrate` to finish and for a healthy Qdrant. `api` starts only after both one-off services exited with 0. This is what `docker compose up` printed on an empty machine (shortened):

```
Container zoomerfume-postgres-1  Healthy
Container zoomerfume-migrate-1   Started
Container zoomerfume-migrate-1   Exited
Container zoomerfume-qdrant-1    Healthy
Container zoomerfume-ingest-1    Started
Container zoomerfume-ingest-1    Exited
Container zoomerfume-api-1       Started
```

A one-off service that fails stops the start: `up` reports `service "migrate" didn't complete successfully: exit 1`, and `api` is created but never started, so it can't run against a database with an old schema. Migrations run in their own service, not in the `api` container. Several API replicas would otherwise each migrate at startup and race. The ingest runs on every `up`, but it skips records whose file hasn't changed, so after the first run it embeds nothing.

The app also checks these things itself. `GET /ready` answers 200 only when Postgres answers, the schema is at the newest migration and the knowledge base collection has points. Otherwise it answers 503 and names the check that failed. `GET /health` only says the process is up. Compose's health check uses `/health`, because nothing waits for the API.

## One image, three services

`migrate`, `ingest` and `api` share one `x-app` block: the same build, image tag, `.env` and log settings. Only the command differs. The image tag comes from `APP_VERSION`, which is also passed into the build:

```bash
APP_VERSION=1.1.0 docker compose up --build    # builds zoomerfume:1.1.0
curl localhost:8000/api/whoami                 # {"hostname": "<container id>", "version": "1.1.0"}
```

Without `APP_VERSION` the tag and the version are `dev`. The Dockerfile stores the build argument as the `APP_VERSION` environment variable, so the version travels with the image. `/api/whoami` and the `X-Served-By` header on every response name the container that answered. In Compose that is the container id.

## Restart test

The data survives a restart:

```bash
# save a note in the web chat, then:
docker compose restart
curl -b jar localhost:8000/api/notes     # the note is still there
```

`restart` restarts every container of the project, including the finished `migrate` and `ingest`. They run again and find nothing to do. It reuses each container's config, so after editing `.env` or `docker-compose.yml` run `docker compose up -d` instead.

## `down` vs `down -v`

| Command | Containers | Network | Volumes (data) |
|---|---|---|---|
| `docker compose stop` | stopped, kept | kept | kept |
| `docker compose down` | removed | removed | kept: the next `up` finds all the data |
| `docker compose down -v` | removed | removed | deleted: the next `up` migrates an empty database and embeds the whole corpus again |
