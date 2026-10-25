# Kubernetes: five breakages

Each breakage was done once on the running kind cluster from [k8s.md](k8s.md): one thing at a time, back to a healthy stack before the next one. For each one the expected result was written down before the run. The actual result and the `kubectl` command that showed it come from the run.

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

**Actual.** _To be filled in from the run._

## 2. Delete all app pods at once

```bash
kubectl delete pods -l app=api
```

**Expected.** All three pods terminate, and the ReplicaSet creates three new ones at once. For a few seconds no api pod is ready, so the `api` Service has no endpoints and requests fail. The port-forward stops. After about 10 seconds all three are ready again. Nothing is lost: the session lives in a cookie and everything else in Postgres, so the web chat continues after a reload. `kubectl get pods` shows three new names, and `kubectl get endpointslices` is empty for a moment.

**Actual.** _To be filled in from the run._

## 3. Scale to 0 and back to 3

```bash
kubectl scale deployment/api --replicas=0
kubectl scale deployment/api --replicas=3
```

**Expected.** At 0 every api pod terminates, and nothing brings them back: 0 is now the desired state, not a failure. `kubectl get deploy api` shows `0/0`. The Service has no endpoints, so requests fail and `kubectl port-forward svc/api` can't find a pod. Postgres, Qdrant and the data are untouched. Back at 3, three new pods start and are ready in a few seconds. A signed-in browser continues after a reload, with its conversations.

**Actual.** _To be filled in from the run._

## 4. Point the image at a tag that doesn't exist

```bash
kubectl set image deployment/api api=zoomerfume:does-not-exist
```

**Expected.** The Deployment starts a rolling update with a new ReplicaSet. With 3 replicas, the default `maxSurge` of 25% rounds up to 1 and `maxUnavailable` of 25% rounds down to 0. So it adds one new pod and keeps all three old pods. The new pod can't get its image: the node doesn't have it, and Docker Hub has no `zoomerfume:does-not-exist`. Its status goes from `ErrImagePull` to `ImagePullBackOff`. The rollout stops there, and the three old pods keep serving, so the web chat keeps working. `kubectl get pods` shows the stuck pod. `kubectl describe pod` and `kubectl get events` show the pull error, and `kubectl rollout status deployment/api` waits and never finishes.

Fix: `kubectl rollout undo deployment/api`, or `kubectl apply -k k8s/`, which sets the image from `kustomization.yaml` again.

**Actual.** _To be filled in from the run._

## 5. Change one character in the Service's selector

```bash
kubectl patch service api -p '{"spec": {"selector": {"app": "apl"}}}'
```

**Expected.** The pods don't change: all three stay Running and Ready, and their logs show nothing new. But the Service now selects no pods, so it has no endpoints. Requests to `api:8000` from inside the cluster fail, and `kubectl port-forward svc/api` can't find a pod for the Service. `kubectl describe service api` shows the new selector and no endpoints, and `kubectl get endpointslices` is empty. `kubectl get pods --show-labels` shows the label the selector no longer matches.

Fix: `kubectl apply -k k8s/`, which puts the selector from `api/service.yaml` back.

**Actual.** _To be filled in from the run._

## Bonus: query the database from inside the cluster

```bash
kubectl exec -it deploy/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```
