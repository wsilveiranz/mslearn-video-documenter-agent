targetScope = 'resourceGroup'

param aiAccountName string
param primaryModelDeploymentName string
param secondaryModelDeploymentName string
param primaryModelCapacity int
param secondaryModelCapacity int

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName
}

resource primaryModel 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: primaryModelDeploymentName
  properties: {
    model: {
      name: 'gpt-5.4-mini'
      format: 'OpenAI'
      version: '2026-03-17'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: primaryModelCapacity
  }
}

resource secondaryModel 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: secondaryModelDeploymentName
  dependsOn: [primaryModel]
  properties: {
    model: {
      name: 'gpt-5.4-nano'
      format: 'OpenAI'
      version: '2026-03-17'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: secondaryModelCapacity
  }
}
