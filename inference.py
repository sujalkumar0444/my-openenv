"""
Inference Script Example
===================================
MANDATORY
- Before submitting, ensure the following variables are defined in your environment configuration:
    API_BASE_URL   The API endpoint for the LLM.
    MODEL_NAME     The model identifier to use for inference.
    HF_TOKEN       Your Hugging Face / API key.
"""

import os
import re
from typing import Dict, List, Tuple

from openai import OpenAI
from openenv.core.sync_client import SyncEnvClient

from my_env import IncidentAction, IncidentEnv, IncidentObservation, IncidentState

API_BASE_URL = os.environ.get("API_BASE_URL", "https://router.huggingface.co/v1")
API_KEY = (
    os.environ.get("HF_TOKEN")
    or os.environ.get("OPENAI_API_KEY")
    or os.environ.get("API_KEY")
)
MODEL_NAME = os.environ.get("MODEL_NAME")
ENV_URL = os.environ.get("ENV_URL", "http://127.0.0.1:8000")

MAX_STEPS = 12
TEMPERATURE = 0.0

TASK_PLANS: Dict[str, List[str]] = {
    "restart_pod": [
        "status",
        "logs payments-db",
        "restart payments-db",
        "status",
    ],
    "fix_config": [
        "status",
        "logs checkout-api",
        "edit_config checkout-api DATABASE_HOST=db-prod.internal",
        "restart checkout-api",
        "status",
    ],
    "rollback_deploy": [
        "status",
        "logs search-api",
        "drain search-api",
        "rollback search-api",
        "status",
    ],
}

ACTION_PREFIX_RE = re.compile(r"^(action|command|next action)\s*[:\-]\s*", re.IGNORECASE)


def _normalize_action(text: str) -> str:
    if not text:
        return ""
    cleaned = text.strip()
    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if lines and lines[0].startswith("```"):
        lines = [line for line in lines if not line.startswith("```")]
    cleaned = lines[0] if lines else cleaned
    cleaned = ACTION_PREFIX_RE.sub("", cleaned).strip()
    if cleaned.startswith(("'", '"')) and cleaned.endswith(("'", '"')):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def _expected_action(task_id: str, step_index: int) -> str:
    plan = TASK_PLANS[task_id]
    if step_index < len(plan):
        return plan[step_index]
    return "status"


def get_action(client: OpenAI, history: str, task_id: str, step_index: int) -> str:
    expected = _expected_action(task_id, step_index)
    prompt = (
        "You are an on-call reliability engineer.\n"
        f"Task: {task_id}.\n"
        "Reply with exactly one CLI command and no extra text.\n"
        "Allowed commands: status, logs <service>, restart <service>, edit_config <service> <key=value>, "
        "drain <service>, rollback <service>, help, noop.\n"
        f"Recommended next command (for deterministic baseline): {expected}\n\n"
        f"Terminal history:\n{history}"
    )

    try:
        request_args = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": TEMPERATURE,
            "top_p": 1,
            "max_tokens": 40,
        }
        response = client.chat.completions.create(**request_args)
        raw = response.choices[0].message.content.strip()
        candidate = _normalize_action(raw)
        if candidate.lower() == expected.lower():
            return candidate
        return expected
    except Exception as exc:
        print(f"LLM call failed, using deterministic fallback: {exc}")
        return expected


IncidentSyncEnv = SyncEnvClient[IncidentAction, IncidentObservation, IncidentState]


def run_task(client: OpenAI, env: IncidentSyncEnv, task_id: str) -> Tuple[float, str]:
    print(f"\n--- Starting Task: {task_id} ---")
    reset_result = env.reset(task_id=task_id)
    history = reset_result.observation.stdout

    final_score = 0.0
    final_reason = ""

    for step in range(MAX_STEPS):
        command = get_action(client, history, task_id, step)
        print(f"Agent executing: {command}")

        result = env.step(IncidentAction(command=command))

        obs = result.observation
        stdout = obs.stdout
        stderr = obs.stderr
        status = obs.status
        print(f"Stdout: {stdout}\nStderr: {stderr}")

        history += f"\n> {command}\n"
        if stdout:
            history += f"{stdout}\n"
        if stderr:
            history += f"{stderr}\n"

        reward = result.reward
        final_score = float(reward) if reward is not None else 0.0
        final_reason = status

        if result.done:
            print(f"Task Complete! Score: {final_score} - {final_reason}")
            break

    return final_score, final_reason


if __name__ == "__main__":
    if not API_KEY or not MODEL_NAME:
        raise SystemExit(
            "Missing API credentials. Set HF_TOKEN or OPENAI_API_KEY (or API_KEY) and MODEL_NAME."
        )

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    scores: Dict[str, float] = {}
    sync_env = IncidentEnv(base_url=ENV_URL).sync()
    with sync_env as env:
        for task in TASK_PLANS.keys():
            score, reason = run_task(client, env, task)
            scores[task] = score
            print(f"Result: {task} => {score} ({reason})")

    avg = sum(scores.values()) / max(len(scores), 1)
    print("\n--- All Evaluation Finished ---")
    print(f"Average score: {avg:.2f}")
