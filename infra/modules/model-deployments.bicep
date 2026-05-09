targetScope = 'resourceGroup'

param aiAccountName string
param gpt4oCapacity int
param gpt4oMiniCapacity int

resource aiAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: aiAccountName
}

resource gpt4o 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: 'gpt-4o'
  properties: {
    model: {
      name: 'gpt-4o'
      format: 'OpenAI'
      version: '2024-11-20'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: gpt4oCapacity
  }
}

resource gpt4oMini 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: aiAccount
  name: 'gpt-4o-mini'
  dependsOn: [gpt4o]
  properties: {
    model: {
      name: 'gpt-4o-mini'
      format: 'OpenAI'
      version: '2024-07-18'
    }
  }
  sku: {
    name: 'GlobalStandard'
    capacity: gpt4oMiniCapacity
  }
}
