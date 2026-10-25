import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://10.135.128.9:11434"
    llm_model: str = "llama3.1"
    nebius_api_key: str | None = None
    nebius_base_url: str = "https://api.tokenfactory.nebius.com/v1/"
    nebius_model: str = "meta-llama/Llama-3.3-70B-Instruct"
    risk_summary_provider: str = "nebius"
    github_token: str | None = None
    github_repo: str | None = None
    aws_region: str = "us-east-1"
    store_backend: str = "dynamo"
    dynamodb_table: str = "costwarden-cleanups"
    checkpoint_backend: str = "memory"
    checkpoint_table: str = "costwarden-checkpoints"
    accounts_file: str = "config/accounts.yaml"
    agent_runtime: str = "local"
    agent_function_prefix: str = "costwarden"
    tf_source: str = "local"
    github_base_branch: str = "main"


def load_settings(env: dict | None = None) -> Settings:
    if env is None:
        try:
            from dotenv import load_dotenv

            load_dotenv()
        except ImportError:
            pass
        env = os.environ
    d = Settings()

    def get(key: str, default):
        return env.get(key) or default

    return Settings(
        llm_provider=get("LLM_PROVIDER", d.llm_provider),
        ollama_base_url=get("OLLAMA_BASE_URL", d.ollama_base_url),
        llm_model=get("LLM_MODEL", d.llm_model),
        nebius_api_key=env.get("NEBIUS_API_KEY") or None,
        nebius_base_url=get("NEBIUS_BASE_URL", d.nebius_base_url),
        nebius_model=get("NEBIUS_MODEL", d.nebius_model),
        risk_summary_provider=get("RISK_SUMMARY_PROVIDER", d.risk_summary_provider),
        github_token=env.get("GITHUB_TOKEN") or None,
        github_repo=env.get("GITHUB_REPO") or None,
        aws_region=get("AWS_REGION", d.aws_region),
        store_backend=get("STORE_BACKEND", d.store_backend),
        dynamodb_table=get("DYNAMODB_TABLE", d.dynamodb_table),
        checkpoint_backend=get("CHECKPOINT_BACKEND", d.checkpoint_backend),
        checkpoint_table=get("CHECKPOINT_TABLE", d.checkpoint_table),
        accounts_file=get("ACCOUNTS_FILE", d.accounts_file),
        agent_runtime=get("AGENT_RUNTIME", d.agent_runtime),
        agent_function_prefix=get("AGENT_FUNCTION_PREFIX", d.agent_function_prefix),
        tf_source=get("TF_SOURCE", d.tf_source),
        github_base_branch=get("GITHUB_BASE_BRANCH", d.github_base_branch),
    )
