targetScope = 'resourceGroup'

@description('Storage account name to grant access to')
param storageAccountName string

@description('Principal ID of the Video Indexer managed identity')
param videoIndexerPrincipalId string

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

// RBAC: Storage Blob Data Contributor → Video Indexer managed identity
resource viStorageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, videoIndexerPrincipalId, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: videoIndexerPrincipalId
    principalType: 'ServicePrincipal'
  }
}
