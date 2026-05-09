targetScope = 'resourceGroup'

param location string
param tags object
param resourceToken string
param principalId string
param principalType string

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ai-${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'S0' }
  kind: 'AIServices'
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: 'ai-${resourceToken}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }

  resource project 'projects' = {
    name: 'video-documenter-project'
    location: location
    identity: { type: 'SystemAssigned' }
    properties: {
      description: 'MS Learn Video Documenter Agent'
      displayName: 'Video Documenter'
    }
  }
}

// RBAC: Cognitive Services User → developer
resource cogServicesUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiAccount.id, principalId, 'a97b65f3-24c7-4388-baec-2e87135dc908')
  scope: aiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    principalId: principalId
    principalType: principalType
  }
}

output aiServicesAccountId string = aiAccount.id
output aiServicesAccountName string = aiAccount.name
output projectEndpoint string = aiAccount::project.properties.endpoints['AI Foundry API']
output openAiEndpoint string = aiAccount.properties.endpoints['OpenAI Language Model Instance API']
