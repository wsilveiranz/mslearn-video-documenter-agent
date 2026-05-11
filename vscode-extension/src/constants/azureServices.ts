import * as vscode from 'vscode';

/**
 * Common Azure service slugs for the ms.service frontmatter field.
 * Each item's `description` holds the slug value used in YAML frontmatter.
 */
export interface AzureServiceItem extends vscode.QuickPickItem {
    /** The ms.service slug value (e.g., "azure-openai"). Empty string for the custom entry option. */
    value: string;
}

export const AZURE_SERVICE_ITEMS: AzureServiceItem[] = [
    { label: '☁️ Azure OpenAI', description: 'azure-openai', detail: 'GPT, DALL-E, and Whisper models hosted on Azure', value: 'azure-openai' },
    { label: '☁️ Azure AI Services', description: 'azure-ai-services', detail: 'Vision, Language, Speech, and Decision APIs', value: 'azure-ai-services' },
    { label: '☁️ Azure AI Foundry', description: 'azure-ai-foundry', detail: 'Build and deploy AI models and agents', value: 'azure-ai-foundry' },
    { label: '🔍 Azure AI Search', description: 'azure-ai-search', detail: 'AI-powered search and indexing service', value: 'azure-ai-search' },
    { label: '🧪 Azure Machine Learning', description: 'azure-machine-learning', detail: 'Train, deploy, and manage ML models', value: 'azure-machine-learning' },
    { label: '🌐 Azure App Service', description: 'azure-app-service', detail: 'Host web apps, REST APIs, and mobile backends', value: 'azure-app-service' },
    { label: '⚡ Azure Functions', description: 'azure-functions', detail: 'Serverless compute for event-driven workloads', value: 'azure-functions' },
    { label: '📦 Azure Container Apps', description: 'azure-container-apps', detail: 'Run containerized apps without managing infrastructure', value: 'azure-container-apps' },
    { label: '🖥️ Azure Kubernetes Service', description: 'azure-kubernetes-service', detail: 'Managed Kubernetes for containerized applications', value: 'azure-kubernetes-service' },
    { label: '🗄️ Azure Storage', description: 'azure-storage', detail: 'Blob, File, Queue, and Table storage', value: 'azure-storage' },
    { label: '🗄️ Azure Cosmos DB', description: 'azure-cosmos-db', detail: 'Globally distributed NoSQL and relational database', value: 'azure-cosmos-db' },
    { label: '🗄️ Azure SQL Database', description: 'azure-sql-database', detail: 'Managed relational SQL database service', value: 'azure-sql-database' },
    { label: '🛠️ Azure DevOps', description: 'azure-devops', detail: 'CI/CD pipelines, repos, boards, and artifacts', value: 'azure-devops' },
    { label: '📊 Azure Monitor', description: 'azure-monitor', detail: 'Full-stack monitoring and diagnostics', value: 'azure-monitor' },
    { label: '🔒 Azure Key Vault', description: 'azure-key-vault', detail: 'Safeguard cryptographic keys and secrets', value: 'azure-key-vault' },
    { label: '📧 Azure Event Hubs', description: 'azure-event-hubs', detail: 'Real-time data streaming platform', value: 'azure-event-hubs' },
    { label: '📧 Azure Service Bus', description: 'azure-service-bus', detail: 'Enterprise message broker with queues and topics', value: 'azure-service-bus' },
    { label: '⚙️ Azure Logic Apps', description: 'azure-logic-apps', detail: 'Automate workflows and integrate services', value: 'azure-logic-apps' },
    { label: '🛡️ Azure API Management', description: 'azure-api-management', detail: 'Publish, secure, and manage APIs', value: 'azure-api-management' },
    { label: '🖲️ Azure Virtual Machines', description: 'azure-virtual-machines', detail: 'On-demand scalable computing resources', value: 'azure-virtual-machines' },
    { label: '💬 Azure Communication Services', description: 'azure-communication-services', detail: 'Voice, video, chat, and SMS capabilities', value: 'azure-communication-services' },
    { label: '🤖 Azure Bot Service', description: 'azure-bot-service', detail: 'Build and deploy intelligent bots', value: 'azure-bot-service' },
    { label: '📐 Power Platform', description: 'power-platform', detail: 'Power Apps, Power Automate, Power BI', value: 'power-platform' },
    { label: '🏢 Microsoft 365', description: 'microsoft-365', detail: 'Productivity and collaboration services', value: 'microsoft-365' },
    { label: '✏️ Other — enter a custom value', description: '', detail: 'Type a custom ms.service slug', value: '' },
];
