#!/usr/bin/env bash
# Install Helm charts for DocumentStream on AKS.
#
# Prerequisites:
#   - kubectl configured for the AKS cluster
#   - helm installed
#
# Usage:
#   ./infra/helm-install.sh          # Install everything
#   ./infra/helm-install.sh redis    # Install only Redis
#   ./infra/helm-install.sh status   # Check status of all releases

set -euo pipefail

# ---- Helm repos ----
add_repos() {
    echo "==> Adding Helm repos..."
    helm repo add bitnami https://charts.bitnami.com/bitnami 2>/dev/null || true
    helm repo add ingress-nginx https://kubernetes.github.io/ingress-nginx 2>/dev/null || true
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
    helm repo add kedacore https://kedacore.github.io/charts 2>/dev/null || true
    helm repo add chaos-mesh https://charts.chaos-mesh.org 2>/dev/null || true
    helm repo update
}

# ---- Individual installs ----

install_redis() {
    echo "==> Installing Redis in documentstream namespace..."
    helm upgrade --install redis bitnami/redis \
        --namespace documentstream \
        --create-namespace \
        --set architecture=standalone \
        --set auth.enabled=false \
        --set master.resources.requests.cpu=50m \
        --set master.resources.requests.memory=64Mi \
        --set master.resources.limits.cpu=200m \
        --set master.resources.limits.memory=128Mi \
        --wait --timeout 120s
    echo "    Redis URL: redis://redis-master.documentstream.svc.cluster.local:6379"
}

install_ingress_nginx() {
    echo "==> Installing ingress-nginx..."
    helm upgrade --install ingress-nginx ingress-nginx/ingress-nginx \
        --namespace ingress-nginx \
        --create-namespace \
        --set controller.resources.requests.cpu=50m \
        --set controller.resources.requests.memory=64Mi \
        --set controller.resources.limits.cpu=200m \
        --set controller.resources.limits.memory=128Mi \
        --set controller.replicaCount=1 \
        --wait --timeout 120s
}

install_keda() {
    echo "==> Installing KEDA..."
    helm upgrade --install keda kedacore/keda \
        --namespace keda \
        --create-namespace \
        --set resources.operator.requests.cpu=50m \
        --set resources.operator.requests.memory=64Mi \
        --set resources.metricServer.requests.cpu=50m \
        --set resources.metricServer.requests.memory=64Mi \
        --wait --timeout 120s
}

install_prometheus() {
    echo "==> Installing kube-prometheus-stack..."
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace monitoring \
        --create-namespace \
        --set prometheus.prometheusSpec.resources.requests.cpu=100m \
        --set prometheus.prometheusSpec.resources.requests.memory=256Mi \
        --set prometheus.prometheusSpec.retention=12h \
        --set grafana.resources.requests.cpu=50m \
        --set grafana.resources.requests.memory=128Mi \
        --set alertmanager.enabled=false \
        --set nodeExporter.enabled=false \
        --wait --timeout 180s
}

install_chaos_mesh() {
    echo "==> Installing Chaos Mesh..."
    helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
        --namespace chaos-mesh \
        --create-namespace \
        --set controllerManager.resources.requests.cpu=25m \
        --set controllerManager.resources.requests.memory=64Mi \
        --set dashboard.resources.requests.cpu=25m \
        --set dashboard.resources.requests.memory=64Mi \
        --wait --timeout 120s
}

# ---- Status ----

show_status() {
    echo "==> Helm releases across all namespaces:"
    helm list --all-namespaces
}

# ---- Main ----

case "${1:-all}" in
    redis)          add_repos; install_redis ;;
    ingress)        add_repos; install_ingress_nginx ;;
    keda)           add_repos; install_keda ;;
    prometheus)     add_repos; install_prometheus ;;
    chaos)          add_repos; install_chaos_mesh ;;
    status)         show_status ;;
    all)
        add_repos
        install_redis
        install_ingress_nginx
        install_keda
        install_prometheus
        install_chaos_mesh
        echo ""
        echo "==> All Helm charts installed. Status:"
        show_status
        ;;
    *)
        echo "Usage: $0 {all|redis|ingress|keda|prometheus|chaos|status}"
        exit 1
        ;;
esac
