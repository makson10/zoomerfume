# Kubernetes: the stack on a local kind cluster

The same image and the same settings that run under Docker Compose also run on a local [kind](https://kind.sigs.k8s.io/) cluster. The app code is the same for both; only what feeds it changes. Compose reads `docker-compose.yml` and `.env`. Kubernetes reads the hand-written manifests in `k8s/` and a git-ignored `k8s/secrets.env`. This page covers how to run it, what each Compose piece became, and the questions a walkthrough raises. The five things we broke on purpose are in [k8s-breakages.md](k8s-breakages.md).

## Run it

Requirements: Docker (Docker Desktop with 8 GB is enough), [kind](https://kind.sigs.k8s.io/docs/user/quick-start/#installation), `kubectl` and an OpenAI API key.

```bash
cp k8s/secrets.env.example k8s/secrets.env    # set DB_PASSWORD, OPENAI_API_KEY and SESSION_SECRET
scripts/kind-up.sh
kubectl port-forward -n zoomerfume svc/api 8000:8000    # then open http://localhost:8000
```

The secrets can also come from the Compose `.env`: `grep -E '^(DB_PASSWORD|OPENAI_API_KEY|SESSION_SECRET)=' .env > k8s/secrets.env`. Stop the Compose `api` first if it holds port 8000.

`scripts/kind-up.sh` goes from nothing to a working stack. On our machine that took 53 seconds from an empty cluster.

1. It creates the cluster `zoomerfume` if it doesn't exist.
2. It builds the app image with the tag from `k8s/kustomization.yaml` (`zoomerfume:1.1.0`), which is also its `APP_VERSION`.
3. It loads that image, `postgres:17.11-alpine` and `qdrant/qdrant:v1.19.1` into the cluster's node, so the node never pulls from a registry. `kind load docker-image` fails on Docker's containerd image store, so the script saves this machine's platform of each image to an archive and loads that instead.
4. It runs `kubectl apply -k k8s/`, then waits for both Jobs to complete and for the `api` rollout.

`kind delete cluster --name zoomerfume` removes everything, the data included.

## What's in `k8s/`

```
k8s/
├── kustomization.yaml     the list of manifests, the namespace, the Secret generator, the app image tag
├── namespace.yaml         zoomerfume
├── configmap.yaml         app-config: plain settings (DB_HOST, DB_PORT, DB_NAME, DB_USER, QDRANT_URL, SECURITY_MODE)
├── secrets.env.example    the keys of app-secrets; the real secrets.env is git-ignored
├── postgres/              Deployment, PersistentVolumeClaim, ClusterIP Service
├── qdrant/                Deployment, PersistentVolumeClaim, ClusterIP Service
├── jobs/                  migrate (alembic upgrade head) and ingest (load the knowledge base)
└── api/                   Deployment (3 replicas) and ClusterIP Service
```

All of it is plain YAML written by hand. Kustomize, built into `kubectl`, only bundles the files. It also sets the namespace on every object, builds the Secret from `secrets.env` and sets the image tag in one place. `kubectl kustomize k8s/` prints the result, and CI checks it against the Kubernetes 1.37 schemas with `kubeconform -strict`.

## From `docker-compose.yml` to Kubernetes

| docker-compose.yml | Kubernetes | Notes |
|---|---|---|
| service `api` | Deployment `api` (3 replicas) + Service `api` | The Deployment keeps three pods running through a ReplicaSet. The Service gives them one stable name and address. |
| services `postgres`, `qdrant` | a Deployment and a ClusterIP Service each | One replica, `strategy: Recreate`, so two pods never share a volume. |
| one-off services `migrate`, `ingest` | Jobs `migrate`, `ingest` | They run to completion and retry on failure. A finished Job deletes itself after an hour, so the next apply runs it again. |
| `build:` and `image: zoomerfume:${APP_VERSION}` | `image: zoomerfume` + `images:` in `kustomization.yaml` | Kubernetes doesn't build images. `kind-up.sh` builds and loads it. |
| `ports: 127.0.0.1:8000:8000` | `kubectl port-forward svc/api 8000:8000` | A ClusterIP Service isn't reachable from the laptop. |
| named volumes | PersistentVolumeClaims `postgres-data`, `qdrant-data` | kind's default StorageClass (`standard`, local-path) creates a folder on the node for each claim. |
| `env_file: .env` | ConfigMap `app-config` + Secret `app-secrets`, both through `envFrom` | Plain settings and secrets are split. |
| `POSTGRES_PASSWORD: ${DB_PASSWORD:?…}` | `env` with `secretKeyRef` / `configMapKeyRef` | The Postgres pod reads the same keys as the app. |
| `healthcheck:` | `readinessProbe` and `livenessProbe` | Probes do something. An unready pod gets no traffic, and a failing liveness probe restarts the container. |
| `restart: unless-stopped` | the controllers and the kubelet | A crashed container is restarted, and a deleted pod is replaced. |
| the default network, service names in DNS | the cluster network, Service names in CoreDNS | See below. |
| `logging:` (json-file rotation) | the kubelet keeps container logs | `kubectl logs`. |
| `depends_on` with conditions | **no direct equivalent** | See the next section. |

## No `depends_on`: how one apply settles on its own

`kubectl apply -k k8s/` creates everything at once, and nothing waits for anything. In Compose, `depends_on` held `api` back until `migrate` and `ingest` had finished. Here three things do that job:

- **Retries.** The Jobs run with `restartPolicy: OnFailure` and `backoffLimit: 10`. `migrate` fails while Postgres is still starting, and `ingest` fails until the tables exist. Each is restarted with a growing delay until it succeeds. Ingest reads Postgres before it embeds anything, so a failed try costs nothing.
- **Readiness.** The api pods start right away, but their readiness probe calls `/ready`. It answers 503 until Postgres answers, the schema is at the newest migration and the knowledge base collection has points. An unready pod is left out of the Service, so no request reaches a pod that can't serve it.
- **Liveness only checks the process.** `/health` doesn't look at Postgres or Qdrant, so a slow database never gets the api pods restarted.

The events of our run from an empty cluster, in order:

```
SuccessfulCreate   job/migrate, job/ingest, and the postgres, qdrant and api pods   (all at once)
BackOff            pod/migrate-…    restarting failed container   (Postgres not up yet)
BackOff            pod/ingest-…     restarting failed container   (Postgres or its tables not ready yet)
Unhealthy          pod/api-…        Readiness probe failed: connection refused   (uvicorn starting)
Unhealthy          pod/postgres-…   Readiness probe failed: no response
Completed          job/migrate      (28 s, after 2 restarts)
Unhealthy          pod/api-…        Readiness probe failed: statuscode: 503   (no knowledge base yet)
Completed          job/ingest       (37 s, after 2 restarts: 208 chunks embedded)
                   deployment "api" successfully rolled out: 3/3 ready
```

## Why the app finds the database without an IP

The app connects to `DB_HOST=postgres`, the same value as in Compose. In Kubernetes the name points at the Service, not at a pod:

- The Service `postgres` gets a stable virtual IP, its ClusterIP. In our run that was `10.96.188.39`. It doesn't change while pods come and go.
- CoreDNS, the cluster's DNS server, answers `postgres.zoomerfume.svc.cluster.local` with that IP. Every pod's `/etc/resolv.conf` points at CoreDNS (the `kube-dns` Service, `10.96.0.10`). The search list there turns the short name `postgres` into the full one:

```
$ kubectl exec -n zoomerfume deploy/api -- sh -c 'cat /etc/resolv.conf; getent hosts postgres'
search zoomerfume.svc.cluster.local svc.cluster.local cluster.local
nameserver 10.96.0.10
10.96.188.39    postgres.zoomerfume.svc.cluster.local
```

- kube-proxy forwards connections to the ClusterIP to a ready pod behind it. The Service's selector `app=postgres` keeps that list of pod IPs (its EndpointSlice) up to date. A recreated Postgres pod gets a new IP, but the app never sees it.

## Where the database password lives

1. **On the laptop:** in `k8s/secrets.env`, which git ignores. It is not in the repo, the image or any manifest.
2. **In the cluster:** `kubectl apply -k` sends it to the API server as the Secret `app-secrets`, which is stored in etcd. The value is base64-encoded, not encrypted: kind doesn't set up encryption at rest. Anyone allowed to read Secrets in the namespace can decode it: `kubectl get secret -n zoomerfume app-secrets -o jsonpath='{.data.DB_PASSWORD}' | base64 -d`.
3. **In the pods:** the kubelet reads the Secret when it starts a container. It becomes the `DB_PASSWORD` environment variable in the api pods and the Jobs (`envFrom`), and `POSTGRES_PASSWORD` in the Postgres pod (`secretKeyRef`).

Environment variables are read when a container starts. After changing `secrets.env` or `configmap.yaml`, run `kubectl apply -k k8s/` and then `kubectl rollout restart -n zoomerfume deployment/api`. Postgres takes its password only when it starts on an empty volume, as in Compose.

`kubectl apply -k` prints `secret/app-secrets configured` on every run, even when nothing changed. Kustomize line-wraps base64 values longer than 76 characters, while the API server stores them on one line, so `kubectl` sees a difference. The values are the same: `kubectl diff -k k8s/` shows nothing.

## Who brings back a deleted pod, and how it knows

The chain of owners: Deployment `api` → ReplicaSet `api-7ddd69c778` (`replicas: 3`) → three pods. Each pod's `metadata.ownerReferences` names its ReplicaSet.

1. The ReplicaSet controller in `kube-controller-manager` watches the pods that match the ReplicaSet's selector (`app=api` plus its `pod-template-hash`). When one is deleted, it counts 2, wants 3 and creates a new pod object: event `SuccessfulCreate`.
2. The scheduler (`kube-scheduler`) picks a node for the pod: event `Scheduled`.
3. The kubelet on that node starts the container: events `Pulled`, `Created` and `Started`.
4. Once the readiness probe passes, the pod joins the Service's endpoints and gets traffic again.

Nobody reacts to the delete itself. The controller keeps comparing the desired state stored in the API server (3 replicas) with what exists, and fixes any difference. That is why scaling to 0 isn't healed: 0 then is the desired state. [k8s-breakages.md](k8s-breakages.md) shows it happen.

## Three replicas serve traffic

`kubectl port-forward svc/api` picks one pod when it starts and sends everything there: six requests through it all came back with the same `X-Served-By`. The proof has to come from inside the cluster, through the Service:

```
$ kubectl exec -n zoomerfume deploy/api -- python -c '
import urllib.request
for _ in range(12):
    print(urllib.request.urlopen("http://api:8000/api/whoami").read().decode())
' | sort | uniq -c
   3 {"hostname":"api-7ddd69c778-6jv4h","version":"1.1.0"}
   7 {"hostname":"api-7ddd69c778-8jg58","version":"1.1.0"}
   2 {"hostname":"api-7ddd69c778-ltp6v","version":"1.1.0"}
```

Each request opens a new connection to the ClusterIP, and kube-proxy picks a ready pod for it. Any replica can serve any request: the session is a signed cookie, and conversations, rate limits and the one-running-turn lock live in Postgres.

## The database is not reachable from outside the cluster

- The `postgres` and `qdrant` Services are `ClusterIP`: their addresses exist only on the cluster network. Nothing is `NodePort`, `LoadBalancer` or behind an Ingress.
- The kind node is a Docker container that publishes one port to the laptop, the Kubernetes API: `docker port zoomerfume-control-plane` prints `6443/tcp -> 127.0.0.1:…`. With Compose stopped, `nc -z localhost 5432` fails.
- Inside the cluster, every pod can connect to Postgres; there is no NetworkPolicy. Someone with cluster credentials can open `kubectl port-forward svc/postgres`, but that is an authenticated tunnel through the API server, not an open port.

## Query the database from inside the cluster

```
$ kubectl exec -n zoomerfume deploy/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "select u.name, n.text, n.status from notes n join users u on u.id = n.user_id"'
 name |                        text                        |  status
------+----------------------------------------------------+-----------
 Mary | Wishlist: Maison Margiela Replica Jazz Club, 30 ml | confirmed
```

## Useful commands

```bash
kubectl config set-context --current --namespace=zoomerfume   # then -n can be left out
kubectl get deploy,rs,pods,jobs,svc,pvc
kubectl get events --sort-by=.lastTimestamp
kubectl describe pod <pod>
kubectl logs deploy/api          # one of the pods; kubectl logs -l app=api --prefix for all three
kubectl logs job/ingest
kubectl rollout status deployment/api
kubectl apply -k k8s/            # back to what the manifests say
```
