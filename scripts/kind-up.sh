#!/usr/bin/env bash
# Run the whole stack on a local kind cluster, from nothing to a working web chat.
#
#   scripts/kind-up.sh
#
# Needs Docker, kind, kubectl and k8s/secrets.env (copy k8s/secrets.env.example).
# Creates the cluster if it doesn't exist, builds the app image, loads every image
# the manifests use into the cluster, applies k8s/ and waits until the API is ready.
set -euo pipefail

CLUSTER=zoomerfume
NAMESPACE=zoomerfume

cd "$(dirname "$0")/.."

if [[ ! -f k8s/secrets.env ]]; then
  echo "k8s/secrets.env is missing: copy k8s/secrets.env.example and fill it in." >&2
  exit 1
fi

# Every image the manifests use, e.g. zoomerfume:1.1.0. The app tag is set once,
# in k8s/kustomization.yaml.
images=$(kubectl kustomize k8s/ |
  awk '{ for (i = 1; i < NF; i++) if ($i == "image:") print $(i + 1) }' | sort -u)
app_image=$(grep '^zoomerfume:' <<< "$images")

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --name "$CLUSTER"
fi

docker build --build-arg APP_VERSION="${app_image#zoomerfume:}" -t "$app_image" .
for image in $images; do
  if [[ $image != "$app_image" ]] && ! docker image inspect "$image" > /dev/null 2>&1; then
    docker pull "$image"
  fi
done
# The nodes get the images from here, so nothing is pulled from a registry.
# `kind load docker-image` fails on Docker's containerd image store, which keeps
# every platform of an image, so save only this machine's platform instead.
platform=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
archive=$(mktemp)
trap 'rm -f "$archive"' EXIT
# shellcheck disable=SC2086
docker save --platform "$platform" -o "$archive" $images
kind load image-archive --name "$CLUSTER" "$archive"

kubectl apply -k k8s/
kubectl -n "$NAMESPACE" wait --for=condition=complete job/migrate job/ingest --timeout=10m
kubectl -n "$NAMESPACE" rollout status deployment/api --timeout=5m
kubectl -n "$NAMESPACE" get pods

echo
echo "Open the web chat: kubectl port-forward -n $NAMESPACE svc/api 8000:8000"
echo "then http://localhost:8000"
