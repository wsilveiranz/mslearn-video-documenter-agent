# Azure resource setup guide

## MS Learn Video Documenter Agent

This guide walks you through provisioning every Azure resource the Video Documenter Agent needs, configuring environment variables, and verifying that each service is reachable. Follow the sections in order — later resources reference earlier ones.

> **Tip:** If you only need local development (no cloud video analysis), skip to [section 8 — Local-only setup](#8-local-only-setup-no-azure-required).

---

## Prerequisites

Before you begin, make sure you have:

- An **Azure subscription** with at least **Contributor** role on the target resource group
- **Azure CLI** v2.60 or later, installed and authenticated:

  ```bash
  az --version
  az login
  ```

- (Optional) Access to [Azure AI Studio](https://ai.azure.com) for portal-based model deployments
- (Optional) Access to [Video Indexer portal](https://www.videoindexer.ai/) for Video Indexer account management

---

## 1. Resource group

Create a single resource group to keep all project resources together. This makes cleanup easy — delete the group when you're done.

### Using Azure CLI

```bash
az group create \
    --name rg-video-documenter \
    --location eastus
```

### Using Azure portal

1. Sign in to the [Azure portal](https://portal.azure.com).
2. Search for **Resource groups** in the top search bar.
3. Select **Create**.
4. Enter `rg-video-documenter` as the name and `East US` as the region.
5. Select **Review + create** → **Create**.

> [!NOTE]
> All resources in this guide use `eastus`. Pick a region that supports Azure AI Services, Video Indexer, and Speech in the same location. Check [Azure products by region](https://azure.microsoft.com/explore/global-infrastructure/products-by-region/) if you need a different region.

---

## 2. Azure AI Foundry project

Azure AI Foundry provides hosted access to GPT-4o and GPT-4o-mini, which power vision analysis and document generation.

### 2.1 Create an AI Services resource

```bash
az cognitiveservices account create \
    --name ai-video-documenter \
    --resource-group rg-video-documenter \
    --kind AIServices \
    --sku S0 \
    --location eastus
```

### 2.2 Deploy the GPT-4o model

Model deployments are managed through the Azure AI Studio portal:

1. Open [Azure AI Studio](https://ai.azure.com).
2. Select your AI Services resource (`ai-video-documenter`), or create a new **project** linked to it.
3. Navigate to **Deployments** → **+ Create deployment**.
4. Choose **gpt-4o** from the model catalog.
5. Set the deployment name to `gpt-4o` (this value becomes `FOUNDRY_MODEL` in your `.env`).
6. Choose a token-per-minute (TPM) quota that fits your workload (start with **30K TPM** for development).
7. Select **Deploy**.

### 2.3 Deploy the GPT-4o-mini model

Repeat the same steps for the lighter model:

1. In Azure AI Studio → **Deployments** → **+ Create deployment**.
2. Choose **gpt-4o-mini**.
3. Set the deployment name to `gpt-4o-mini`.
4. Allocate TPM quota (start with **60K TPM** — mini is cheaper).
5. Select **Deploy**.

> [!NOTE]
> GPT-4o-mini is used by the Structure and Editor agents. GPT-4o handles Extraction (vision) and Writer tasks. Both deployments must exist for cloud mode.

### 2.4 Get endpoint and assign roles

```bash
# Get the endpoint URL
az cognitiveservices account show \
    --name ai-video-documenter \
    --resource-group rg-video-documenter \
    --query "properties.endpoint" -o tsv
```

Save this as `FOUNDRY_PROJECT_ENDPOINT`.

#### Assign RBAC roles for your developer identity

The app uses `DefaultAzureCredential` — no API keys needed. Grant your identity the required role:

```bash
# Get your user object ID
USER_ID=$(az ad signed-in-user show --query "id" -o tsv)

# Grant Cognitive Services User role (allows model inference calls)
az role assignment create \
    --assignee $USER_ID \
    --role "Cognitive Services User" \
    --scope "/subscriptions/<SUB_ID>/resourceGroups/rg-video-documenter/providers/Microsoft.CognitiveServices/accounts/ai-video-documenter"
```

> [!NOTE]
> Role assignments can take up to 5 minutes to propagate. If you get 401 errors immediately after assigning, wait and retry.

#### Assign roles for Foundry hosted agent (managed identity)

When deploying as a Foundry hosted agent, the compute has a system-assigned managed identity. Grant it the same role:

```bash
# Get the managed identity principal ID from your Foundry agent deployment
# (available after deployment — see Foundry documentation)
AGENT_PRINCIPAL_ID=<managed-identity-principal-id>

az role assignment create \
    --assignee $AGENT_PRINCIPAL_ID \
    --role "Cognitive Services User" \
    --scope "/subscriptions/<SUB_ID>/resourceGroups/rg-video-documenter/providers/Microsoft.CognitiveServices/accounts/ai-video-documenter"
```

---

## 3. Azure Blob Storage

Blob Storage stages uploaded video files and stores extracted keyframe images during processing.

### 3.1 Create a storage account

Storage account names must be **lowercase**, **3–24 characters**, and **alphanumeric only** (no hyphens or underscores).

```bash
az storage account create \
    --name stvideodocumenter \
    --resource-group rg-video-documenter \
    --sku Standard_LRS \
    --kind StorageV2 \
    --location eastus
```

### 3.2 Create a blob container

```bash
az storage container create \
    --name video-documenter \
    --account-name stvideodocumenter
```

### 3.3 Assign roles for Blob Storage

Instead of connection strings, use identity-based access:

```bash
# Get the storage account resource ID
STORAGE_ID=$(az storage account show \
    --name stvideodocumenter \
    --resource-group rg-video-documenter \
    --query "id" -o tsv)

# Get your user object ID
USER_ID=$(az ad signed-in-user show --query "id" -o tsv)

# Grant Storage Blob Data Contributor (read/write blobs)
az role assignment create \
    --assignee $USER_ID \
    --role "Storage Blob Data Contributor" \
    --scope $STORAGE_ID
```

Get the account URL for your `.env`:

```bash
az storage account show \
    --name stvideodocumenter \
    --resource-group rg-video-documenter \
    --query "primaryEndpoints.blob" -o tsv
```

Save as `BLOB_ACCOUNT_URL`.

#### For Foundry hosted agent (managed identity)

```bash
az role assignment create \
    --assignee $AGENT_PRINCIPAL_ID \
    --role "Storage Blob Data Contributor" \
    --scope $STORAGE_ID
```

---

## 4. Azure AI Speech

Azure AI Speech provides fast, high-quality transcription with speaker diarization. It's used in cloud mode only — local mode falls back to OpenAI Whisper.

### 4.1 Create a Speech resource

```bash
az cognitiveservices account create \
    --name speech-video-documenter \
    --resource-group rg-video-documenter \
    --kind SpeechServices \
    --sku S0 \
    --location eastus
```

### 4.2 Get endpoint and assign roles

```bash
# Get the endpoint
az cognitiveservices account show \
    --name speech-video-documenter \
    --resource-group rg-video-documenter \
    --query "properties.endpoint" -o tsv
```

Save as `SPEECH_SERVICE_ENDPOINT`.

```bash
# Get your user object ID (if not already set)
USER_ID=$(az ad signed-in-user show --query "id" -o tsv)

# Grant Cognitive Services Speech User role
az role assignment create \
    --assignee $USER_ID \
    --role "Cognitive Services Speech User" \
    --scope "/subscriptions/<SUB_ID>/resourceGroups/rg-video-documenter/providers/Microsoft.CognitiveServices/accounts/speech-video-documenter"
```

#### For Foundry hosted agent (managed identity)

```bash
az role assignment create \
    --assignee $AGENT_PRINCIPAL_ID \
    --role "Cognitive Services Speech User" \
    --scope "/subscriptions/<SUB_ID>/resourceGroups/rg-video-documenter/providers/Microsoft.CognitiveServices/accounts/speech-video-documenter"
```

---

## 5. Azure Video Indexer

Video Indexer performs full video analysis — scene detection, keyframe extraction, OCR, transcript, entity recognition, and more. Setup is more involved than other resources because Video Indexer uses its own resource provider.

### 5.1 Register the resource provider

The `Microsoft.VideoIndexer` provider may not be registered in your subscription by default:

```bash
az provider register --namespace Microsoft.VideoIndexer

# Check registration status (wait until "Registered")
az provider show --namespace Microsoft.VideoIndexer --query "registrationState" -o tsv
```

> [!NOTE]
> Registration can take a few minutes. Poll with the `az provider show` command until it returns `Registered`.

### 5.2 Create a Video Indexer account (ARM-based)

#### Using Azure CLI

```bash
az resource create \
    --resource-group rg-video-documenter \
    --resource-type Microsoft.VideoIndexer/accounts \
    --name vi-video-documenter \
    --location eastus \
    --properties '{
        "mediaServices": {},
        "storageServices": {
            "resourceId": "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/rg-video-documenter/providers/Microsoft.Storage/storageAccounts/stvideodocumenter"
        }
    }'
```

Replace `<SUBSCRIPTION_ID>` with your Azure subscription ID. Get it with:

```bash
az account show --query "id" -o tsv
```

#### Using Azure portal

1. Sign in to the [Azure portal](https://portal.azure.com).
2. Search for **Video Indexer** in the top search bar.
3. Select **Create**.
4. Fill in:
   - **Resource group:** `rg-video-documenter`
   - **Name:** `vi-video-documenter`
   - **Region:** `East US`
   - **Storage account:** Select `stvideodocumenter` (created in step 3)
5. Select **Review + create** → **Create**.

### 5.3 Link to AI Services (enhanced features)

Linking Video Indexer to your AI Services resource unlocks advanced capabilities (custom models, higher-quality OCR). You can do this in the Azure portal:

1. Open the `vi-video-documenter` resource in the [Azure portal](https://portal.azure.com).
2. Go to **Settings** → **AI Services**.
3. Select **Link** and choose `ai-video-documenter` (created in step 2).
4. Confirm the link.

### 5.4 Get account ID and resource ID

```bash
# Get the Video Indexer resource ID
az resource show \
    --resource-group rg-video-documenter \
    --resource-type Microsoft.VideoIndexer/accounts \
    --name vi-video-documenter \
    --query "id" -o tsv
```

The result looks like:

```
/subscriptions/<sub-id>/resourceGroups/rg-video-documenter/providers/Microsoft.VideoIndexer/accounts/vi-video-documenter
```

Save this full string as `VIDEO_INDEXER_RESOURCE_ID`.

To get the **Account ID** (a GUID):

```bash
az resource show \
    --resource-group rg-video-documenter \
    --resource-type Microsoft.VideoIndexer/accounts \
    --name vi-video-documenter \
    --query "properties.accountId" -o tsv
```

Save this as `VIDEO_INDEXER_ACCOUNT_ID`.

### 5.5 Authentication

The app uses `DefaultAzureCredential` to generate ARM access tokens for the Video Indexer API automatically. No static API key is needed.

Grant the Contributor role:

```bash
VI_RESOURCE_ID=$(az resource show \
    --resource-group rg-video-documenter \
    --resource-type Microsoft.VideoIndexer/accounts \
    --name vi-video-documenter \
    --query "id" -o tsv)

# Get your user object ID (if not already set)
USER_ID=$(az ad signed-in-user show --query "id" -o tsv)

az role assignment create \
    --assignee $USER_ID \
    --role "Contributor" \
    --scope $VI_RESOURCE_ID
```

#### For Foundry hosted agent (managed identity)

```bash
az role assignment create \
    --assignee $AGENT_PRINCIPAL_ID \
    --role "Contributor" \
    --scope $VI_RESOURCE_ID
```

---

## 6. Environment configuration

### 6.1 Create a `.env` file

Create a `.env` file in the project root (`backend/.env` or the root directory, depending on your runner). Use the template below and fill in the values you collected from earlier steps.

```bash
# ──────────────────────────────────────
# Processing Mode
# ──────────────────────────────────────
# "cloud" — uses Azure Video Indexer + Speech for video analysis
# "local" — uses FFmpeg + PySceneDetect + Whisper (no cloud video services)
PROCESSING_MODE=cloud

# ──────────────────────────────────────
# Azure AI Foundry
# ──────────────────────────────────────
# Endpoint from: az cognitiveservices account show (section 2.4)
FOUNDRY_PROJECT_ENDPOINT=https://ai-video-documenter.cognitiveservices.azure.com/

# Deployment name you chose in Azure AI Studio (section 2.2)
FOUNDRY_MODEL=gpt-4o
FOUNDRY_MODEL_MINI=gpt-4o-mini

# ──────────────────────────────────────
# Azure Blob Storage
# ──────────────────────────────────────
# Account URL from: az storage account show (section 3.3)
# Uses DefaultAzureCredential — no connection string needed
BLOB_ACCOUNT_URL=https://stvideodocumenter.blob.core.windows.net

# Container name created in section 3.2
BLOB_CONTAINER_NAME=video-documenter

# ──────────────────────────────────────
# Azure AI Speech (cloud mode only)
# ──────────────────────────────────────
# Endpoint from: az cognitiveservices account show (section 4.2)
# Uses DefaultAzureCredential — no API key needed
SPEECH_SERVICE_ENDPOINT=https://speech-video-documenter.cognitiveservices.azure.com

# Region must match the --location used when creating the resource
SPEECH_SERVICE_REGION=eastus

# ──────────────────────────────────────
# Azure Video Indexer (cloud mode only)
# ──────────────────────────────────────
# Account ID GUID from: az resource show ... properties.accountId (section 5.4)
VIDEO_INDEXER_ACCOUNT_ID=your-account-id-guid

# Full ARM resource ID from: az resource show ... id (section 5.4)
VIDEO_INDEXER_RESOURCE_ID=/subscriptions/<sub-id>/resourceGroups/rg-video-documenter/providers/Microsoft.VideoIndexer/accounts/vi-video-documenter

# Location (section 5.4)
VIDEO_INDEXER_LOCATION=trial

# ──────────────────────────────────────
# Local mode settings (when PROCESSING_MODE=local)
# ──────────────────────────────────────
# Whisper model size: tiny, base, small, medium, large
WHISPER_MODEL=base

# Path to FFmpeg binary (must be on PATH or provide absolute path)
FFMPEG_PATH=ffmpeg

# ──────────────────────────────────────
# Output
# ──────────────────────────────────────
OUTPUT_DIRECTORY=./output
```

> [!CAUTION]
> Never commit `.env` to source control. The project `.gitignore` should already exclude it. Verify with `git check-ignore .env` before committing.

### 6.2 Verify configuration

Run the following Python snippet to verify each service is reachable. Save it as a temporary script or run it interactively:

```python
"""Verify Azure resource connectivity using DefaultAzureCredential."""
import os
import sys
from dotenv import load_dotenv

load_dotenv()

errors = []

# 1. Check AI Foundry endpoint
endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "")
if not endpoint:
    errors.append("FOUNDRY_PROJECT_ENDPOINT is missing")
else:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient

        credential = DefaultAzureCredential()
        print(f"✅ AI Foundry: endpoint configured ({endpoint})")
    except Exception as e:
        errors.append(f"AI Foundry: {e}")

# 2. Check Blob Storage
account_url = os.getenv("BLOB_ACCOUNT_URL", "")
container = os.getenv("BLOB_CONTAINER_NAME", "video-documenter")
if not account_url:
    errors.append("BLOB_ACCOUNT_URL is missing")
else:
    try:
        from azure.identity import DefaultAzureCredential
        from azure.storage.blob import BlobServiceClient

        credential = DefaultAzureCredential()
        blob_client = BlobServiceClient(account_url=account_url, credential=credential)
        container_client = blob_client.get_container_client(container)
        props = container_client.get_container_properties()
        print(f"✅ Blob Storage: container '{container}' exists")
    except Exception as e:
        errors.append(f"Blob Storage: {e}")

# 3. Check Speech Service
speech_endpoint = os.getenv("SPEECH_SERVICE_ENDPOINT", "")
speech_region = os.getenv("SPEECH_SERVICE_REGION", "")
if not speech_endpoint or not speech_region:
    print("⏭️  Speech Service: skipped (endpoint/region not set — OK for local mode)")
else:
    print(f"✅ Speech Service: endpoint configured for region '{speech_region}'")

# 4. Check Video Indexer
vi_account = os.getenv("VIDEO_INDEXER_ACCOUNT_ID", "")
vi_resource = os.getenv("VIDEO_INDEXER_RESOURCE_ID", "")
if not vi_account or not vi_resource:
    print("⏭️  Video Indexer: skipped (account/resource not set — OK for local mode)")
else:
    print(f"✅ Video Indexer: account ID '{vi_account[:8]}...' configured (ARM token via DefaultAzureCredential)")

# Summary
if errors:
    print(f"\n❌ {len(errors)} issue(s) found:")
    for err in errors:
        print(f"   - {err}")
    sys.exit(1)
else:
    print("\n🎉 All configured services are reachable!")
```

Install the verification dependencies if needed:

```bash
pip install python-dotenv azure-identity azure-storage-blob
```

---

## 7. Cost estimates

Approximate costs for **development usage** (small-scale, a few videos per day). Prices are USD and subject to change — check [Azure pricing](https://azure.microsoft.com/pricing/) for current rates.

| Service | Pricing model | Approximate cost |
|---------|--------------|-----------------|
| **GPT-4o** | Per token | ~$2.50 / 1M input tokens, ~$10.00 / 1M output tokens |
| **GPT-4o-mini** | Per token | ~$0.15 / 1M input tokens, ~$0.60 / 1M output tokens |
| **Blob Storage** (Standard LRS) | Per GB/month | ~$0.018 / GB / month |
| **AI Speech** | Per audio hour | ~$1.00 / hour |
| **Video Indexer** (basic) | Per minute of video | ~$0.035 / minute |
| **Video Indexer** (advanced/AI) | Per minute of video | ~$0.18 / minute |

**Example:** Processing a 10-minute screen recording in cloud mode costs roughly:

- Video Indexer (basic): ~$0.35
- Speech transcription: ~$0.17
- GPT-4o (vision + writing): ~$0.10–$0.50 depending on output length
- **Total: ~$0.60–$1.00 per video**

> [!TIP]
> Use `PROCESSING_MODE=local` during development to avoid Video Indexer and Speech charges. You'll still incur GPT-4o costs for vision analysis and document generation.

---

## 8. Local-only setup (no Azure required)

You can run the agent pipeline with **zero Azure dependencies** (except an LLM endpoint) by using local mode.

### 8.1 Set local mode

In your `.env` file:

```bash
PROCESSING_MODE=local
```

### 8.2 Install local dependencies

| Dependency | Install command | Purpose |
|-----------|----------------|---------|
| **FFmpeg** | `winget install FFmpeg` (Windows) / `brew install ffmpeg` (macOS) / `apt install ffmpeg` (Linux) | Frame extraction, audio extraction |
| **PySceneDetect** | `pip install scenedetect[opencv]` | Scene boundary detection |
| **OpenAI Whisper** | `pip install openai-whisper` | Local speech-to-text |

Verify FFmpeg is available:

```bash
ffmpeg -version
```

### 8.3 LLM options for local mode

Local mode still requires an LLM for vision analysis and document generation. You have several options:

| Option | Endpoint | Notes |
|--------|---------|-------|
| **Azure AI Foundry** (recommended) | `https://your-resource.cognitiveservices.azure.com/` | Best quality; requires Azure subscription |
| **OpenAI direct** | `https://api.openai.com/v1` | No Azure needed; requires OpenAI API key |
| **Ollama** (fully offline) | `http://localhost:11434/v1` | Free; use `llava` for vision, `llama3` for text |

For Ollama (fully offline setup):

```bash
# Install Ollama
winget install Ollama.Ollama  # Windows
# or: curl -fsSL https://ollama.com/install.sh | sh  # Linux/macOS

# Pull models
ollama pull llava       # Vision model
ollama pull llama3.1    # Text generation
```

### 8.4 Minimal `.env` for local mode

```bash
PROCESSING_MODE=local
FOUNDRY_PROJECT_ENDPOINT=https://ai-video-documenter.cognitiveservices.azure.com/
FOUNDRY_MODEL=gpt-4o
WHISPER_MODEL=base
FFMPEG_PATH=ffmpeg
OUTPUT_DIRECTORY=./output
```

---

## 9. Cleanup

When you're done with the project, delete all resources in one command:

```bash
az group delete --name rg-video-documenter --yes --no-wait
```

This removes every resource created in this guide.

---

## Authentication overview

This project uses **`DefaultAzureCredential`** from the Azure Identity SDK for all Azure service connections. This provides a unified credential chain that works across environments:

| Environment | Credential used | Setup required |
|---|---|---|
| **Local development** | Azure CLI (`az login`) | Sign in with `az login` + RBAC roles |
| **Local development (VS Code)** | VS Code Azure extension | Sign in to Azure in VS Code + RBAC roles |
| **CI/CD** | Environment variables | Set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` |
| **Foundry hosted agent** | System-assigned managed identity | Enable managed identity + RBAC roles |

### Required RBAC roles summary

| Azure resource | Role | Scope |
|---|---|---|
| AI Services (Foundry) | `Cognitive Services User` | AI Services account |
| Blob Storage | `Storage Blob Data Contributor` | Storage account |
| AI Speech | `Cognitive Services Speech User` | Speech account |
| Video Indexer | `Contributor` | Video Indexer account |

---

## Troubleshooting

### "AuthenticationFailed" when calling AI Services

- Ensure you're signed in: `az login`
- Verify role assignment: `az role assignment list --assignee $(az ad signed-in-user show --query id -o tsv) --scope <resource-id> --output table`
- Role assignments can take up to 5 minutes to propagate
- If using managed identity, verify it's enabled on the compute and has the correct role
- Make sure the endpoint URL includes the trailing `/` — some SDKs require it.

### Model deployment not found

- Deployment names are case-sensitive. Check the exact name in Azure AI Studio → **Deployments**.
- Make sure the deployment status is **Succeeded**, not **Creating** or **Failed**.
- The `FOUNDRY_MODEL` env var must match the deployment name, not the model name (e.g., `gpt-4o` if that's what you named it).

### Blob Storage "ContainerNotFound"

- Verify the container exists: `az storage container list --account-name stvideodocumenter --query "[].name" -o tsv`
- Verify you have `Storage Blob Data Contributor` role on the storage account.

### Speech Service "401 Unauthorized"

- Verify you have `Cognitive Services Speech User` role on the Speech resource.
- Confirm the endpoint and region match: the endpoint must belong to the resource in the specified region.
- Role assignments can take up to 5 minutes to propagate.

### Video Indexer "ResourceProviderNotRegistered"

- Register the provider: `az provider register --namespace Microsoft.VideoIndexer`
- Wait for status to change to `Registered` (can take 2–5 minutes).

### FFmpeg not found (local mode)

- Ensure `ffmpeg` is on your system PATH, or set `FFMPEG_PATH` to the full path (e.g., `C:\tools\ffmpeg\bin\ffmpeg.exe`).
- Test with: `ffmpeg -version`

### Whisper running out of memory (local mode)

- Use a smaller model: set `WHISPER_MODEL=tiny` or `WHISPER_MODEL=base` in `.env`.
- The `large` model needs ~10 GB VRAM. For CPU-only machines, stick with `tiny` or `base`.
