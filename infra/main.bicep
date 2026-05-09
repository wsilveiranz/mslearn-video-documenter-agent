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

@description('Primary model deployment capacity (thousands of tokens per minute)')
param primaryModelCapacity int = 30

@description('Secondary model deployment capacity (thousands of tokens per minute)')
param secondaryModelCapacity int = 60

@description('Enable model deployments (disable to deploy models manually via Portal/CLI)')
param enableModelDeployments bool = false

@description('Deployment name for the primary model (must match what backend expects)')
param primaryModelDeploymentName string = 'gpt-4.1-mini'

@description('Deployment name for the secondary/mini model')
param secondaryModelDeploymentName string = 'gpt-4.1-mini'

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
  }
}

// Model deployments must be a separate nested deployment because ARM
// pre-flight validation cannot validate deployments against an account
// that doesn't exist yet (produces opaque error 715-123420).
module modelDeployments 'modules/model-deployments.bicep' = if (enableModelDeployments) {
  scope: rg
  name: 'model-deployments'
  params: {
    aiAccountName: aiFoundry.outputs.aiServicesAccountName
    primaryModelDeploymentName: primaryModelDeploymentName
    secondaryModelDeploymentName: secondaryModelDeploymentName
    primaryModelCapacity: primaryModelCapacity
    secondaryModelCapacity: secondaryModelCapacity
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

// Cross-service RBAC: Video Indexer MI → Storage Blob Data Contributor
module crossServiceRbac 'modules/cross-service-rbac.bicep' = if (enableVideoIndexer) {
  scope: rg
  name: 'cross-service-rbac'
  params: {
    storageAccountName: storage.outputs.storageAccountName
    videoIndexerPrincipalId: videoIndexer!.outputs.principalId
  }
}

// ═══════════════════════════════════════════════════════════
// OUTPUTS (used by azd to populate .env)
// ═══════════════════════════════════════════════════════════

output AZURE_RESOURCE_GROUP string = resourceGroupName

// AI Foundry
output FOUNDRY_PROJECT_ENDPOINT string = aiFoundry.outputs.projectEndpoint
output FOUNDRY_MODEL string = primaryModelDeploymentName
output FOUNDRY_MODEL_MINI string = secondaryModelDeploymentName

// Blob Storage
output BLOB_ACCOUNT_URL string = storage.outputs.blobEndpoint
output BLOB_CONTAINER_NAME string = 'video-documenter'

// Speech Service
output SPEECH_SERVICE_ENDPOINT string = speech.outputs.endpoint
output SPEECH_SERVICE_REGION string = location

// Video Indexer
output VIDEO_INDEXER_ACCOUNT_ID string = enableVideoIndexer ? videoIndexer!.outputs.accountId : ''
output VIDEO_INDEXER_RESOURCE_ID string = enableVideoIndexer ? videoIndexer!.outputs.resourceId : ''
output VIDEO_INDEXER_LOCATION string = location
