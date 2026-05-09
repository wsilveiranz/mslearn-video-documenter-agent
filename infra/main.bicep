targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the environment used for resource naming')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Id of the user or app to assign application roles')
param principalId string

@description('Principal type - use User for developer, ServicePrincipal for managed identity')
@allowed(['User', 'ServicePrincipal'])
param principalType string = 'User'

@description('GPT-4o model deployment capacity (thousands of tokens per minute)')
param gpt4oCapacity int = 30

@description('GPT-4o-mini model deployment capacity (thousands of tokens per minute)')
param gpt4oMiniCapacity int = 60

@description('Enable Video Indexer provisioning (requires Microsoft.VideoIndexer provider)')
param enableVideoIndexer bool = true

var resourceToken = uniqueString(subscription().id, environmentName, location)
var tags = { 'azd-env-name': environmentName }
var resourceGroupName = 'rg-${environmentName}'

// Resource Group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// ═══════════════════════════════════════════════════════════
// AI FOUNDRY (Account + Project + Model Deployments)
// ═══════════════════════════════════════════════════════════

module aiFoundry 'modules/ai-foundry.bicep' = {
  scope: rg
  name: 'ai-foundry'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    principalType: principalType
    gpt4oCapacity: gpt4oCapacity
    gpt4oMiniCapacity: gpt4oMiniCapacity
  }
}

// ═══════════════════════════════════════════════════════════
// BLOB STORAGE (Video files + keyframe images)
// ═══════════════════════════════════════════════════════════

module storage 'modules/storage.bicep' = {
  scope: rg
  name: 'storage'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    principalType: principalType
    containerName: 'video-documenter'
  }
}

// ═══════════════════════════════════════════════════════════
// SPEECH SERVICE (Transcription)
// ═══════════════════════════════════════════════════════════

module speech 'modules/speech.bicep' = {
  scope: rg
  name: 'speech'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    principalType: principalType
  }
}

// ═══════════════════════════════════════════════════════════
// VIDEO INDEXER (Video analysis — scenes, OCR, keyframes)
// ═══════════════════════════════════════════════════════════

module videoIndexer 'modules/video-indexer.bicep' = if (enableVideoIndexer) {
  scope: rg
  name: 'video-indexer'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    principalType: principalType
    storageAccountId: storage.outputs.storageAccountId
  }
}

// ═══════════════════════════════════════════════════════════
// OUTPUTS (used by azd to populate .env)
// ═══════════════════════════════════════════════════════════

output AZURE_RESOURCE_GROUP string = resourceGroupName

// AI Foundry
output FOUNDRY_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output FOUNDRY_MODEL string = 'gpt-4o'
output FOUNDRY_MODEL_MINI string = 'gpt-4o-mini'

// Blob Storage
output BLOB_ACCOUNT_URL string = storage.outputs.blobEndpoint
output BLOB_CONTAINER_NAME string = 'video-documenter'

// Speech Service
output SPEECH_SERVICE_ENDPOINT string = speech.outputs.endpoint
output SPEECH_SERVICE_REGION string = location

// Video Indexer
output VIDEO_INDEXER_ACCOUNT_ID string = enableVideoIndexer ? videoIndexer.outputs.accountId : ''
output VIDEO_INDEXER_RESOURCE_ID string = enableVideoIndexer ? videoIndexer.outputs.resourceId : ''
output VIDEO_INDEXER_LOCATION string = location
