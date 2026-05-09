targetScope = 'resourceGroup'

param location string
param tags object
param resourceToken string
param principalId string
param principalType string
param storageAccountId string

resource videoIndexer 'Microsoft.VideoIndexer/accounts@2025-04-01' = {
  name: 'vi-${resourceToken}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    storageServices: {
      resourceId: storageAccountId
    }
  }
}

// RBAC: Contributor → developer on Video Indexer account
resource viContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(videoIndexer.id, principalId, 'b24988ac-6180-42a0-ab88-20f7382dd24c')
  scope: videoIndexer
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b24988ac-6180-42a0-ab88-20f7382dd24c')
    principalId: principalId
    principalType: principalType
  }
}

output accountId string = videoIndexer.properties.accountId
output resourceId string = videoIndexer.id
output name string = videoIndexer.name
output principalId string = videoIndexer.identity.principalId
