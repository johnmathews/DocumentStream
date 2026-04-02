#!/usr/bin/env bash
# Provision Azure infrastructure for DocumentStream.
#
# What this creates:
#   - Resource Group: DocumentStream (westeurope)
#   - ACR: acrdocumentstream (Basic)
#   - AKS: DocumentStreamManagedCluster (Free tier, 2x Standard_B2s_v2)
#   - PostgreSQL Flexible Server: documentstream-pg (Burstable B1ms, pg16)
#   - Storage Account + Blob Container (Standard_LRS)
#
# Prerequisites:
#   - az cli logged in
#   - Sufficient quota (4 vCPU in westeurope)
#   - PG_PASSWORD environment variable set
#
# Usage:
#   export PG_PASSWORD="your-secure-password"
#   ./infra/setup.sh

set -euo pipefail

RG="DocumentStream"
LOCATION="westeurope"
ACR_NAME="acrdocumentstream"
AKS_NAME="DocumentStreamManagedCluster"
PG_NAME="documentstream-pg"
PG_ADMIN="documentstream"
PG_PASSWORD="${PG_PASSWORD:?Set PG_PASSWORD environment variable before running this script}"
STORAGE_NAME="documentstream"
BLOB_CONTAINER="documents"

echo "==> Creating resource group..."
az group create --name "$RG" --location "$LOCATION" --output none

echo "==> Registering resource providers..."
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.ContainerService --wait
az provider register --namespace Microsoft.Compute --wait
az provider register --namespace Microsoft.DBforPostgreSQL --wait

echo "==> Creating ACR..."
az acr create --name "$ACR_NAME" --resource-group "$RG" --sku Basic --output none

echo "==> Creating AKS cluster (this takes 5-10 minutes)..."
az aks create \
    --resource-group "$RG" \
    --name "$AKS_NAME" \
    --node-count 2 \
    --node-vm-size Standard_B2s_v2 \
    --attach-acr "$ACR_NAME" \
    --generate-ssh-keys \
    --tier free \
    --output none

echo "==> Getting AKS credentials..."
az aks get-credentials --resource-group "$RG" --name "$AKS_NAME" --overwrite-existing

echo "==> Creating PostgreSQL Flexible Server..."
az postgres flexible-server create \
    --resource-group "$RG" \
    --name "$PG_NAME" \
    --location "$LOCATION" \
    --admin-user "$PG_ADMIN" \
    --admin-password "$PG_PASSWORD" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --version 16 \
    --storage-size 32 \
    --public-access 0.0.0.0 \
    --output none

echo "==> Enabling pgvector extension..."
az postgres flexible-server parameter set \
    --resource-group "$RG" \
    --server-name "$PG_NAME" \
    --name azure.extensions \
    --value VECTOR \
    --output none

echo "==> Creating Storage Account..."
az storage account create \
    --name "$STORAGE_NAME" \
    --resource-group "$RG" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --output none

echo "==> Creating Blob Container..."
az storage container create \
    --name "$BLOB_CONTAINER" \
    --account-name "$STORAGE_NAME" \
    --output none

echo ""
echo "==> Infrastructure provisioned!"
echo "    Resource Group:  $RG"
echo "    ACR:             $ACR_NAME.azurecr.io"
echo "    AKS:             $AKS_NAME (2 nodes)"
echo "    PostgreSQL:      $PG_NAME.postgres.database.azure.com"
echo "    Storage:         $STORAGE_NAME.blob.core.windows.net/$BLOB_CONTAINER"
echo ""
echo "Next steps:"
echo "  1. Run ./infra/helm-install.sh"
echo "  2. Initialize DB schema: psql \$DATABASE_URL -f src/worker/schema.sql"
echo "  3. Build and push images (Stage 4)"
echo "  4. kubectl apply -k k8s/base/"
