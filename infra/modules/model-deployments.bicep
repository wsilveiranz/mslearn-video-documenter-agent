targetScope = 'resourceGroup'

param aiAccountName string
param primaryModelCapacity int
param secondaryModelCapacity int

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName
}

resource gpt54mini 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: 'gpt-5-4-mini'
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

resource gpt54nano 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: 'gpt-5-4-nano'
  dependsOn: [gpt54mini]
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
