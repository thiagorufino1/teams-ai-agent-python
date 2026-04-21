"""
Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the MIT License.
"""

class Config:
    """Agent Configuration"""

    def __init__(self, env):
        def get_required(key):
            val = env.get(key)
            if not val:
                raise ValueError(
                    f"\n[ERRO DE CONFIGURAÇÃO] Variável obrigatória '{key}' não encontrada.\n"
                    "Certifique-se de que:\n"
                    "1. Você criou o arquivo 'env/.env.local.user' a partir do '.example'.\n"
                    "2. Você preencheu essa variável no arquivo '.user'.\n"
                    "3. Você executou o comando Provision/Deploy no Teams Toolkit.\n"
                )
            return val

        self.port = int(env.get("PORT", 3978))
        self.azure_openai_api_key = get_required("AZURE_OPENAI_API_KEY")
        self.azure_openai_deployment_name = get_required("AZURE_OPENAI_DEPLOYMENT_NAME")
        self.azure_openai_endpoint = get_required("AZURE_OPENAI_ENDPOINT")
        self.azure_openai_api_version = env.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")
        self.ai_feedback_loop_enabled = env.get("M365_AGENT_FEEDBACK_LOOP", "true").lower() == "true"
        self.ai_generated_label_enabled = env.get("M365_AGENT_AI_LABEL", "true").lower() == "true"
        self.sensitivity_name = env.get("M365_AGENT_SENSITIVITY_NAME", "Internal")
        self.sensitivity_type = env.get("M365_AGENT_SENSITIVITY_TYPE", "https://schema.org/Message")
        self.sensitivity_schema_type = env.get("M365_AGENT_SENSITIVITY_SCHEMA_TYPE", "CreativeWork")
        self.max_history_turns = int(env.get("M365_AGENT_MAX_HISTORY_TURNS", 20))
