targetScope = 'resourceGroup'

param location string
param tags object
param resourceToken string
param principalId string
param principalType string

resource speechAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'speech-${resourceToken}'
  location: location
  tags: tags
  sku: { name: 'S0' }
  kind: 'SpeechServices'
  properties: {
    customSubDomainName: 'speech-${resourceToken}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

// RBAC: Cognitive Services Speech User → developer
resource speechUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(speechAccount.id, principalId, 'f2dc8367-1007-4938-bd23-fe263f013447')
  scope: speechAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'f2dc8367-1007-4938-bd23-fe263f013447')
    principalId: principalId
    principalType: principalType
  }
}

output endpoint string = speechAccount.properties.endpoint
output name string = speechAccount.name
