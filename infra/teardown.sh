#!/usr/bin/env bash
# Manage DocumentStream Azure infrastructure lifecycle.
#
# Usage:
#   ./infra/teardown.sh destroy   # Delete everything (irreversible)
#   ./infra/teardown.sh stop      # Stop AKS + PostgreSQL (save costs)
#   ./infra/teardown.sh start     # Restart AKS + PostgreSQL

set -euo pipefail

RG="DocumentStream"
AKS_NAME="DocumentStreamManagedCluster"
PG_NAME="documentstream-pg"

stop() {
    echo "==> Stopping AKS cluster..."
    az aks stop --resource-group "$RG" --name "$AKS_NAME" --no-wait
    echo "==> Stopping PostgreSQL..."
    az postgres flexible-server stop --resource-group "$RG" --name "$PG_NAME" --no-wait
    echo "    Stopped. Cost is now ~€0.01/hr (disk only)."
    echo "    Restart with: $0 start"
}

start() {
    echo "==> Starting AKS cluster..."
    az aks start --resource-group "$RG" --name "$AKS_NAME" --no-wait
    echo "==> Starting PostgreSQL..."
    az postgres flexible-server start --resource-group "$RG" --name "$PG_NAME" --no-wait
    echo "    Starting up. AKS takes 2-3 minutes to become ready."
    echo "    Check with: kubectl get nodes"
}

destroy() {
    echo "WARNING: This will delete ALL resources in resource group '$RG'."
    echo "This is irreversible. All data will be lost."
    read -p "Type 'yes' to confirm: " confirm
    if [ "$confirm" = "yes" ]; then
        echo "==> Deleting resource group $RG..."
        az group delete --name "$RG" --yes --no-wait
        echo "    Deletion in progress. Takes a few minutes."
    else
        echo "    Aborted."
    fi
}

case "${1:-}" in
    stop)    stop ;;
    start)   start ;;
    destroy) destroy ;;
    *)
        echo "Usage: $0 {stop|start|destroy}"
        echo ""
        echo "  stop     Stop AKS + PostgreSQL (saves cost, keeps data)"
        echo "  start    Restart AKS + PostgreSQL"
        echo "  destroy  Delete everything (irreversible)"
        exit 1
        ;;
esac
