# Microsoft 365 Agent for Teams

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python)
![SDK](https://img.shields.io/badge/M365%20Agents%20SDK-0.8.x-purple)
![License](https://img.shields.io/badge/License-MIT-green)
![Azure](https://img.shields.io/badge/Azure-OpenAI-orange?logo=microsoft-azure)

Agente conversacional para Microsoft Teams construído com o **Microsoft 365 Agents SDK** e **Azure OpenAI**. Oferece respostas em streaming, memória de conversa por sessão e metadados nativos do Teams — pronto para provisionamento no Azure via Bicep e CI/CD com GitHub Actions.

---

## Sumário

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Início Rápido](#início-rápido)
- [Configuração](#configuração)
- [Execução e Depuração](#execução-e-depuração)
- [Implantação no Azure](#implantação-no-azure)
- [Estrutura do Repositório](#estrutura-do-repositório)
- [Referências](#referências)

---

## Visão Geral

Este projeto entrega uma base de produção para agentes no Teams com:

| Funcionalidade | Descrição |
|---|---|
| **Streaming incremental** | Tokens chegam progressivamente ao usuário sem aguardar a resposta completa |
| **Memória de conversa** | Histórico de mensagens mantido por sessão com limite configurável |
| **Feedback loop** | Botões de like/dislike nativos ao final de cada resposta |
| **Badge "Gerado por IA"** | Indicação visual nativa do Teams em todas as respostas do agente |
| **Sensitivity label** | Metadado de classificação de sensibilidade configurável por ambiente |
| **Prompt externalizado** | Sistema de prompt e parâmetros do modelo em arquivos independentes do código |
| **Branding configurável** | Nome, descrição e informações do desenvolvedor via variáveis de ambiente |
| **Retry automático** | Backoff exponencial em falhas transientes do Azure OpenAI (429, 5xx) |

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    Usuário no Teams                     │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Azure Bot Service (Teams Channel)          │
│         Autenticação via User Assigned Managed Identity │
└──────────────────────────┬──────────────────────────────┘
                           │  POST /api/messages
                           ▼
┌─────────────────────────────────────────────────────────┐
│          Azure App Service (Python / aiohttp)           │
│                                                         │
│  app.py ──► JWT Middleware ──► agent.py                 │
│                                    │                    │
│              ConversationState ◄───┤                    │
│              (histórico/sessão)    │                    │
└──────────────────────────┬──────────────────────────────┘
                           │  Streaming
                           ▼
┌─────────────────────────────────────────────────────────┐
│                   Azure OpenAI Service                  │
│              (chat.completions com stream=True)         │
└─────────────────────────────────────────────────────────┘
```

### Componentes Principais

| Arquivo | Responsabilidade |
|---|---|
| [src/app.py](src/app.py) | Servidor HTTP aiohttp — expõe `/api/messages`, `/healthz` |
| [src/agent.py](src/agent.py) | Handlers do agente, streaming, retry e memória de conversa |
| [src/config.py](src/config.py) | Leitura e validação de variáveis de ambiente com erros descritivos |
| [src/sdk_workarounds.py](src/sdk_workarounds.py) | Patches de compatibilidade para o SDK 0.8.x |
| [src/prompts/chat/skprompt.txt](src/prompts/chat/skprompt.txt) | Prompt de sistema do agente |
| [src/prompts/chat/config.json](src/prompts/chat/config.json) | Parâmetros de completion (temperatura, max_tokens, etc.) |
| [appPackage/manifest.json](appPackage/manifest.json) | Manifesto do app Teams com substituição de variáveis `${{VAR}}` |
| [infra/azure.bicep](infra/azure.bicep) | Infrastructure as Code — provisionamento dos recursos Azure |
| [m365agents.yml](m365agents.yml) | Workflow principal de provision/deploy/publish do toolkit |

---

## Início Rápido

### 1. Clonar o repositório

```bash
git clone <url-do-repositorio>
cd teams-ai-agent-python
```

### 2. Criar arquivos de ambiente a partir dos templates

```bash
cp env/.env.local.example           env/.env.local
cp env/.env.local.user.example      env/.env.local.user
cp env/.env.playground.example      env/.env.playground
cp env/.env.playground.user.example env/.env.playground.user
```

### 3. Preencher as credenciais do Azure OpenAI

Abra `env/.env.local.user` e `env/.env.playground.user` e preencha:

```env
SECRET_AZURE_OPENAI_API_KEY=<sua-chave-aqui>
AZURE_OPENAI_ENDPOINT=https://<seu-recurso>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=<nome-do-deployment>
```

> **Atenção:** Nunca versione arquivos `*.user`. Eles estão listados no `.gitignore` e contêm credenciais sensíveis.

### 4. (Opcional) Personalizar a identidade do agente

Em `env/.env.local`, ajuste o branding conforme necessário:

```env
APP_SHORT_NAME=Nome do Bot
APP_FULL_NAME=Nome Completo do Bot
APP_DEVELOPER_NAME=Nome da Empresa
APP_DEVELOPER_WEBSITE=https://suaempresa.com
APP_DEVELOPER_PRIVACY_URL=https://suaempresa.com/privacidade
APP_DEVELOPER_TERMS_URL=https://suaempresa.com/termos
```

### 5. Iniciar em modo de depuração

Abra o projeto no VS Code e pressione **F5**. O toolkit criará automaticamente o `venv` e instalará as dependências.

---

## Configuração

### Hierarquia de Arquivos de Ambiente

| Arquivo | Versionado | Conteúdo |
|---|---|---|
| `env/.env.local.example` | Sim | Template de variáveis não-secretas |
| `env/.env.local.user.example` | Sim | Template de variáveis secretas |
| `env/.env.local` | **Não** | Branding, IDs gerados pelo toolkit |
| `env/.env.local.user` | **Não** | Chaves de API, credenciais |
| `env/.env.dev` | Sim | Parâmetros de deploy (subscription, resource group) |
| `.env` (raiz) | **Não** | Gerado automaticamente pelo toolkit — não editar |

### Variáveis Obrigatórias

| Variável | Descrição |
|---|---|
| `AZURE_OPENAI_API_KEY` | Chave de acesso ao recurso Azure OpenAI |
| `AZURE_OPENAI_ENDPOINT` | URL do recurso (`https://<nome>.openai.azure.com/`) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Nome do deployment do modelo (ex: `gpt-4o`) |

### Variáveis de Comportamento

| Variável | Padrão | Descrição |
|---|---|---|
| `AZURE_OPENAI_API_VERSION` | `2024-12-01-preview` | Versão da API Azure OpenAI |
| `M365_AGENT_FEEDBACK_LOOP` | `true` | Habilita botões like/dislike |
| `M365_AGENT_AI_LABEL` | `true` | Exibe badge "Gerado por IA" |
| `M365_AGENT_SENSITIVITY_NAME` | `Internal` | Nome do rótulo de sensibilidade |
| `M365_AGENT_MAX_HISTORY_TURNS` | `20` | Número máximo de turnos no histórico |

### Variáveis de Identidade e Branding

Injetadas no `appPackage/manifest.json` via substituição `${{VAR}}` pelo toolkit.

| Variável | Onde aparece no Teams |
|---|---|
| `APP_SHORT_NAME` | Nome do bot no chat |
| `APP_FULL_NAME` | Nome na página de instalação |
| `APP_DESCRIPTION_SHORT` | Descrição na listagem de apps |
| `APP_DESCRIPTION_FULL` | Descrição completa na página do app |
| `APP_DEVELOPER_NAME` | Campo "Desenvolvido por" |
| `APP_DEVELOPER_WEBSITE` | Link do desenvolvedor |
| `APP_DEVELOPER_PRIVACY_URL` | Link para política de privacidade |
| `APP_DEVELOPER_TERMS_URL` | Link para termos de uso |

### Customização do Prompt

O prompt de sistema e os parâmetros do modelo são externalizados e não requerem alteração de código:

- **[src/prompts/chat/skprompt.txt](src/prompts/chat/skprompt.txt)** — instruções de comportamento do agente
- **[src/prompts/chat/config.json](src/prompts/chat/config.json)** — parâmetros de completion (temperatura, `max_tokens`, etc.)

---

## Execução e Depuração

### Playground (validação rápida sem Teams)

No VS Code, selecione **`Debug in Microsoft 365 Agents Playground`** e pressione **F5**.

Ideal para validar:
- Recebimento e resposta de mensagens
- Streaming de texto
- Lógica dos handlers

> O Playground não renderiza feedback loop, badge "Gerado por IA" e sensitivity label. Para validar essas funcionalidades, utilize o Teams.

### Microsoft Teams (validação completa)

No VS Code, selecione uma das configurações abaixo e pressione **F5**:

| Configuração | Uso recomendado |
|---|---|
| `Debug in Teams (Edge)` | Depuração via navegador Edge |
| `Debug in Teams (Chrome)` | Depuração via navegador Chrome |
| `Debug in Teams (Desktop)` | Depuração no cliente desktop do Teams |

Use o Teams para validar:
- Fluxo completo de instalação do app
- Streaming no cliente real
- Feedback loop, badge de IA e sensitivity label

---

## Implantação no Azure

### Recursos Provisionados

O comando **Provision** do toolkit cria os seguintes recursos na sua subscription:

| Recurso | SKU | Descrição |
|---|---|---|
| App Service Plan | Linux B1 | Plano de hospedagem do bot |
| Web App | Python 3.11 | Instância do bot em execução |
| User Assigned Managed Identity | — | Identidade sem senha para autenticação |
| Azure Bot Service | — | Registro do bot no Bot Framework vinculado ao Teams |

### CI/CD com GitHub Actions

O workflow [.github/workflows/provision_and_deploy.yml](.github/workflows/provision_and_deploy.yml) executa provision e deploy automaticamente.

Configure os seguintes secrets no repositório GitHub:

| Secret | Descrição |
|---|---|
| `AZURE_CLIENT_ID` | Client ID da Service Principal |
| `AZURE_TENANT_ID` | Tenant ID do Azure AD |
| `AZURE_SUBSCRIPTION_ID` | ID da subscription alvo |
| `SECRET_AZURE_OPENAI_API_KEY` | Chave de API do Azure OpenAI |

---

## Estrutura do Repositório

```
teams-ai-agent-python/
├── .github/
│   └── workflows/
│       └── provision_and_deploy.yml   # Pipeline CI/CD
├── appPackage/
│   ├── manifest.json                  # Manifesto do app Teams
│   ├── color.png                      # Ícone colorido (192x192)
│   └── outline.png                    # Ícone outline (32x32)
├── devTools/                          # Ferramentas locais do toolkit
├── env/
│   ├── .env.local.example             # Template de variáveis locais
│   ├── .env.local.user.example        # Template de secrets locais
│   └── .env.dev                       # Variáveis de deploy Azure
├── infra/
│   ├── azure.bicep                    # Template de provisionamento
│   ├── azure.parameters.json          # Parâmetros do Bicep
│   └── botRegistration/
│       └── azurebot.bicep             # Registro do Azure Bot
├── src/
│   ├── app.py                         # Servidor HTTP e roteamento
│   ├── agent.py                       # Lógica do agente e streaming
│   ├── config.py                      # Validação de configuração
│   ├── sdk_workarounds.py             # Patches de compatibilidade SDK
│   ├── requirements.txt               # Dependências Python
│   └── prompts/
│       └── chat/
│           ├── skprompt.txt           # Prompt de sistema
│           └── config.json            # Parâmetros de completion
├── m365agents.yml                     # Workflow do toolkit (provision/deploy)
├── .gitignore
└── README.md
```

---

## Referências

- [Microsoft 365 Agents SDK for Python](https://github.com/microsoft/agents-for-python)
- [Microsoft 365 Agents Toolkit](https://aka.ms/teams-toolkit)
- [Azure OpenAI Service](https://learn.microsoft.com/azure/ai-services/openai/)
- [Azure Bot Service](https://learn.microsoft.com/azure/bot-service/)
- [Teams App Manifest Schema](https://learn.microsoft.com/microsoftteams/platform/resources/schema/manifest-schema)
- [Bicep Documentation](https://learn.microsoft.com/azure/azure-resource-manager/bicep/)

---

## Licença

Distribuído sob a licença MIT. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
