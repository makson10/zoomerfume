# Kubernetes: five breakages

Each breakage was done once on the running kind cluster from [k8s.md](k8s.md): one thing at a time, back to a healthy stack before the next one. The expected results were written down and committed before the run. The actual results, the `kubectl` commands that showed them and the fixes come from the run on 2026-10-26.

All commands use the `zoomerfume` namespace. Set it once to keep them short:

```bash
kubectl config set-context --current --namespace=zoomerfume
```

The healthy state: `kubectl get deploy,pods` shows `api` 3/3, `postgres` 1/1, `qdrant` 1/1, and the `migrate` and `ingest` Jobs completed.

## 1. Delete a pod

```bash
kubectl delete pod <one of the api pods>
```

**Expected.** The Deployment's ReplicaSet wants 3 api pods and now sees 2, so it creates a new one right away. The scheduler puts it on the node, and the kubelet starts it. The new pod has a new name and a young age. It stays unready for a few seconds, until `/ready` passes. Meanwhile the Service sends requests only to the two ready pods, so the web chat keeps working. Only a reply that was streaming from the deleted pod breaks. If `kubectl port-forward` was connected to that pod, it stops, because a port-forward is tied to one pod. `kubectl get pods` shows the new pod, and `kubectl get events` shows `SuccessfulCreate` from the ReplicaSet.

**Actual.** As expected. The new pod `api-7ddd69c778-b4pkw` existed one second after the delete. `kubectl get events` showed the chain: `SuccessfulCreate` from the ReplicaSet, `Scheduled` from the scheduler, then `Pulled` ("already present on machine", because `kind-up.sh` loaded the image), `Created` and `Started` from the kubelet. One readiness check failed while uvicorn was starting, and the pod was 1/1 Ready after about 7 seconds. The port-forward had been connected to the deleted pod and stopped with `error: lost connection to pod`.

**Told us:** `kubectl get pods` (a new name, `0/1` then `1/1`) and `kubectl get events`.

**Fix:** none needed: the Deployment heals itself. Restart the port-forward.

## 2. Delete all app pods at once

```bash
kubectl delete pods -l app=api
```

**Expected.** All three pods terminate, and the ReplicaSet creates three new ones at once. For a few seconds no api pod is ready, so the `api` Service has no endpoints and requests fail. The port-forward stops. After about 10 seconds all three are ready again. Nothing is lost: the session lives in a cookie and everything else in Postgres, so the web chat continues after a reload. `kubectl get pods` shows three new names, and `kubectl get endpointslices` is empty for a moment.

**Actual.** The ReplicaSet created three new pods in the same second the old ones started terminating. For a moment `kubectl get pods` listed six: three `Terminating`, three `ContainerCreating`. A loop in the Postgres pod requested `http://api:8000/health` every half second. It failed for about 7 seconds and then succeeded again. All three new pods were Ready after about 14 seconds. One thing differed: `kubectl get endpointslices` never looked empty. It lists every pod address, ready or not, so it went straight from the old IPs to the new ones. The gap only showed in the failed requests.

**Told us:** `kubectl get pods`, `kubectl get events` (three `Killing`, three `SuccessfulCreate`) and the request loop.

**Fix:** none needed. Restart the port-forward.

## 3. Scale to 0 and back to 3

```bash
kubectl scale deployment/api --replicas=0
kubectl scale deployment/api --replicas=3
```

**Expected.** At 0 every api pod terminates, and nothing brings them back: 0 is now the desired state, not a failure. `kubectl get deploy api` shows `0/0`. The Service has no endpoints, so requests fail and `kubectl port-forward svc/api` can't find a pod. Postgres, Qdrant and the data are untouched. Back at 3, three new pods start and are ready in a few seconds. A signed-in browser continues after a reload, with its conversations.

**Actual.** As expected. `kubectl get deploy api` showed `0/0`, `kubectl get pods -l app=api` said `No resources found`, and `kubectl describe service api` showed an empty `Endpoints:`. A request to `api:8000` from the Postgres pod failed at once with `Connection refused`, because a Service without endpoints rejects connections. `kubectl port-forward svc/api` waited 60 seconds for a pod and then gave up with `error: timed out waiting for the condition`. Back at 3, the same ReplicaSet scaled up, and all three pods were Ready 6 seconds later. A signed-in session still got its user from `/api/me` and its conversation from `/api/conversations`.

**Told us:** `kubectl get deploy`, `kubectl describe service api` and `kubectl get events` (`Scaled down replica set api-7ddd69c778 from 3 to 0`, then `from 0 to 3`).

**Fix:** `kubectl scale deployment/api --replicas=3`, or `kubectl apply -k k8s/`.

## 4. Point the image at a tag that doesn't exist

```bash
kubectl set image deployment/api api=zoomerfume:does-not-exist
```

**Expected.** The Deployment starts a rolling update with a new ReplicaSet. With 3 replicas, the default `maxSurge` of 25% rounds up to 1 and `maxUnavailable` of 25% rounds down to 0. So it adds one new pod and keeps all three old pods. The new pod can't get its image: the node doesn't have it, and Docker Hub has no `zoomerfume:does-not-exist`. Its status goes from `ErrImagePull` to `ImagePullBackOff`. The rollout stops there, and the three old pods keep serving, so the web chat keeps working. `kubectl get pods` shows the stuck pod. `kubectl describe pod` and `kubectl get events` show the pull error, and `kubectl rollout status deployment/api` waits and never finishes.

**Actual.** As expected. A new ReplicaSet `api-d5fcd8f5c` got one pod, which went `ErrImagePull` and then `ImagePullBackOff`. The old ReplicaSet kept 3/3 Ready, and `/api/whoami` through the Service kept answering from the old pods with version `1.1.0`. `kubectl rollout status` stopped at `1 out of 3 new replicas have been updated` and timed out. The pod's events named the cause: an image without a registry means Docker Hub, and Docker Hub has no such repository.

```
Failed to pull image "zoomerfume:does-not-exist": failed to pull and unpack image
"docker.io/library/zoomerfume:does-not-exist": ... pull access denied, repository does not exist
```

`kubectl apply -k k8s/` fixed it. The Deployment went back to its old ReplicaSet, and the stuck pod was deleted.

**Told us:** `kubectl get pods` (`ImagePullBackOff`), `kubectl describe pod` (the pull error), `kubectl get rs` (new ReplicaSet 0/1, old one 3/3) and `kubectl rollout status`.

**Fix:** `kubectl apply -k k8s/`, which sets the image from `kustomization.yaml` again, or `kubectl rollout undo deployment/api`.

## 5. Change one character in the Service's selector

```bash
kubectl patch service api -p '{"spec": {"selector": {"app": "apl"}}}'
```

**Expected.** The pods don't change: all three stay Running and Ready, and their logs show nothing new. But the Service now selects no pods, so it has no endpoints. Requests to `api:8000` from inside the cluster fail, and `kubectl port-forward svc/api` can't find a pod for the Service. `kubectl describe service api` shows the new selector and no endpoints, and `kubectl get endpointslices` is empty. `kubectl get pods --show-labels` shows the label the selector no longer matches.

**Actual.** As expected, with one surprise: nothing complained. The pods stayed 3/3 Ready, their logs had no new lines, and `kubectl get events` had no event about it. Only the Service showed it: `kubectl describe service api` had `Selector: app=apl` and an empty `Endpoints:`, and `kubectl get endpointslices` showed `<unset>`. A request from the Postgres pod got `Connection refused`. `kubectl port-forward svc/api` looks up a pod with the Service's selector, waited 60 seconds and gave up with `error: timed out waiting for the condition`. `kubectl get pods --show-labels` showed the pods' label `app=api` next to the selector's `app=apl`. `kubectl apply -k k8s/` printed `service/api configured` and brought the three endpoints back.

**Told us:** `kubectl describe service api` and `kubectl get endpointslices`, compared with `kubectl get pods --show-labels`. `get pods`, `logs` and `get events` all looked healthy, so a Service with no endpoints is the thing to check when healthy pods get no traffic.

**Fix:** `kubectl apply -k k8s/`, which puts the selector from `api/service.yaml` back.

## Bonus: query the database from inside the cluster

`psql` runs in the Postgres pod, which already has the user and the database in its environment:

```
$ kubectl exec deploy/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
    -c "select u.name, n.text, n.status from notes n join users u on u.id = n.user_id"'
 name |                        text                        |  status
------+----------------------------------------------------+-----------
 Mary | Wishlist: Maison Margiela Replica Jazz Club, 30 ml | confirmed
```

For an interactive session: `kubectl exec -it deploy/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'`.
