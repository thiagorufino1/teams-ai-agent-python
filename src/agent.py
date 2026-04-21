import os
import asyncio
import json
import logging
from dotenv import load_dotenv

from microsoft_agents.hosting.core import (
    AgentApplication,
    TurnState,
    TurnContext,
    MemoryStorage,
)
from microsoft_agents.activity import (
    load_configuration_from_env,
    ActivityTypes,
    SensitivityUsageInfo,
)
from microsoft_agents.hosting.aiohttp import CloudAdapter
from microsoft_agents.authentication.msal import MsalConnectionManager
from openai import AsyncAzureOpenAI

from config import Config
from sdk_workarounds import apply_sdk_workarounds

load_dotenv()
apply_sdk_workarounds()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0  # seconds


async def _call_openai_with_retry(client, *, stream: bool, messages, model, **params):
    """Call Azure OpenAI with exponential backoff on transient errors."""
    from openai import APIStatusError, APIConnectionError

    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            return await client.chat.completions.create(
                messages=messages,
                model=model,
                stream=stream,
                **params,
            )
        except APIStatusError as exc:
            if exc.status_code not in _RETRY_STATUSES:
                raise
            last_exc = exc
        except APIConnectionError as exc:
            last_exc = exc

        delay = _RETRY_BASE_DELAY * (2 ** attempt)
        logger.warning(
            "OpenAI transient error (attempt %d/%d), retrying in %.1fs: %s",
            attempt + 1,
            _MAX_RETRIES,
            delay,
            last_exc,
        )
        await asyncio.sleep(delay)

    raise last_exc

# Load configuration
config = Config(os.environ)
agents_sdk_config = load_configuration_from_env(os.environ)

client = AsyncAzureOpenAI(
    api_version=config.azure_openai_api_version,
    api_key=config.azure_openai_api_key,
    azure_endpoint=config.azure_openai_endpoint,
    azure_deployment=config.azure_openai_deployment_name,
)

def load_prompt_config(prompt_name: str):
    # Get the absolute path to the prompt directory
    prompt_dir = os.path.join(os.path.dirname(__file__), "prompts", prompt_name)
    
    # Load system prompt template
    with open(os.path.join(prompt_dir, "skprompt.txt"), "r", encoding="utf-8") as f:
        system_prompt = f.read().strip()
    
    # Load completion configuration
    with open(os.path.join(prompt_dir, "config.json"), "r", encoding="utf-8") as f:
        config_data = json.load(f)
        
    return system_prompt, config_data.get("completion", {})

# Load initial prompt configuration
prompt_text, prompt_params = load_prompt_config("chat")

# Define storage and application
storage = MemoryStorage()
connection_manager = MsalConnectionManager(**agents_sdk_config)
adapter = CloudAdapter(connection_manager=connection_manager)

agent_app = AgentApplication[TurnState](
    storage=storage, 
    adapter=adapter, 
    **agents_sdk_config
)

@agent_app.conversation_update("membersAdded")
async def on_members_added(context: TurnContext, _state: TurnState):
    await context.send_activity("Olá! Como posso ajudar você hoje?")

# Listen for ANY message to be received. MUST BE AFTER ANY OTHER MESSAGE HANDLERS
@agent_app.activity(ActivityTypes.message)
async def on_message(context: TurnContext, state: TurnState):
    response = context.streaming_response
    chunk_count = 0
    channel_id = getattr(context.activity, "channel_id", None)
    activity_id = getattr(context.activity, "id", None)
    is_webchat = channel_id == "webchat"

    processed_ids: list = state.conversation.get_value("processed_activity_ids", list) or []
    if activity_id and activity_id in processed_ids:
        logger.info("dedupe: ignoring duplicate activity_id=%s channel_id=%s", activity_id, channel_id)
        return
    if activity_id:
        processed_ids.append(activity_id)
        state.conversation.set_value("processed_activity_ids", processed_ids[-50:])

    # Load conversation history from state
    history: list = state.conversation.get_value("history", list) or []

    user_text = context.activity.text or ""
    history.append({"role": "user", "content": user_text})

    # Trim to keep only the last MAX_HISTORY_TURNS messages
    if len(history) > config.max_history_turns:
        history = history[-config.max_history_turns:]

    logger.info(
        "stream start: %s",
        json.dumps(
            {
                "feedback_loop": config.ai_feedback_loop_enabled,
                "generated_by_ai_label": config.ai_generated_label_enabled,
                "sensitivity_name": config.sensitivity_name,
                "history_turns": len(history),
                "channel_id": channel_id,
                "activity_id": activity_id,
                "conversation_id": getattr(context.activity.conversation, "id", None),
            }
        ),
    )

    if not is_webchat:
        response.set_feedback_loop(config.ai_feedback_loop_enabled)
        if config.ai_feedback_loop_enabled:
            response.set_feedback_loop_type("default")
        response.set_generated_by_ai_label(config.ai_generated_label_enabled)
        response.set_sensitivity_label(
            SensitivityUsageInfo(
                type=config.sensitivity_type,
                schema_type=config.sensitivity_schema_type,
                name=config.sensitivity_name,
            )
        )
        response.queue_informative_update("Generating response...")
        logger.debug('stream: queued informative update "Generating response..."')

    assistant_message = ""
    try:
        if is_webchat:
            result = await _call_openai_with_retry(
                client,
                stream=False,
                messages=[{"role": "system", "content": prompt_text}, *history],
                model=config.azure_openai_deployment_name,
                **prompt_params,
            )
            assistant_message = result.choices[0].message.content or ""
            if assistant_message:
                await context.send_activity(assistant_message)
                logger.info("webchat: sent non-streaming response (%d chars)", len(assistant_message))
        else:
            result = await _call_openai_with_retry(
                client,
                stream=True,
                messages=[{"role": "system", "content": prompt_text}, *history],
                model=config.azure_openai_deployment_name,
                **prompt_params,
            )

            async for chunk in result:
                if not chunk.choices:
                    continue

                content = chunk.choices[0].delta.content
                if content:
                    chunk_count += 1
                    assistant_message += content
                    response.queue_text_chunk(content)
                    logger.debug("stream: queued chunk #%d (%d chars)", chunk_count, len(content))
        if not assistant_message:
            fallback = "No content was returned by the model."
            assistant_message = fallback
            if is_webchat:
                await context.send_activity(fallback)
                logger.warning("webchat: model returned no content")
            else:
                response.queue_text_chunk(fallback)
                logger.warning("stream: model returned no content")
    except Exception as exc:
        logger.error("OpenAI error: %s", exc, exc_info=True)
        fallback = (
            "Desculpe, ocorreu um erro ao gerar a resposta. "
            "Verifique os logs do App Service para detalhes."
        )
        assistant_message = fallback
        if is_webchat:
            await context.send_activity(fallback)
        else:
            response.queue_text_chunk(fallback)
    finally:
        logger.info(
            "stream end: %s",
            json.dumps({"chunk_count": chunk_count, "message_length": len(response.get_message() or "")}),
        )
        if not is_webchat:
            await response.end_stream()
            logger.debug("stream: end_stream completed")

    # Save assistant response to history and persist
    if assistant_message:
        history.append({"role": "assistant", "content": assistant_message})
    state.conversation.set_value("history", history)

@agent_app.error
async def on_error(context: TurnContext, error: Exception):
    logger.error("unhandled turn error: %s", error, exc_info=True)
    await context.send_activity("The agent encountered an error or bug.")
