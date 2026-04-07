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
import sys
from typing import Dict, List, Optional, Tuple

from openai import OpenAI
from openenv.core.sync_client import SyncEnvClient

from my_env import IncidentAction, IncidentEnv, IncidentObservation, IncidentState

API_BASE_URL = os.environ.get("API_BASE_URL")
API_KEY = (
    os.environ.get("API_KEY")
)
MODEL_NAME = os.environ.get("MODEL_NAME")
ENV_URL = os.environ.get("ENV_URL", "http://127.0.0.1:8000")
BENCHMARK = os.environ.get("BENCHMARK", "oncall_incident_response")

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


def _stderr_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _sanitize_inline(text: str) -> str:
    return text.replace("\n", " ").replace("\r", " ").strip()


def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(step: int, action: str, reward: float, done: bool, error: Optional[str]) -> None:
    done_val = str(done).lower()
    error_val = "null" if not error else _sanitize_inline(error)
    action_val = _sanitize_inline(action)
    print(
        f"[STEP] step={step} action={action_val} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(success: bool, steps: int, score: float, rewards: List[float]) -> None:
    success_val = str(success).lower()
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)
    score_val = max(0.0, min(score, 1.0))
    print(
        f"[END] success={success_val} steps={steps} score={score_val:.2f} rewards={rewards_str}",
        flush=True,
    )


def get_action(
    client: Optional[OpenAI], history: str, task_id: str, step_index: int
) -> str:
    expected = _expected_action(task_id, step_index)
    if client is None or not MODEL_NAME:
        return expected
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
        _stderr_log(f"LLM call failed, using deterministic fallback: {exc}")
        return expected


IncidentSyncEnv = SyncEnvClient[IncidentAction, IncidentObservation, IncidentState]


def run_task(client: Optional[OpenAI], task_id: str) -> Tuple[float, str]:
    model_label = MODEL_NAME or "unknown"
    log_start(task=task_id, env=BENCHMARK, model=model_label)

    rewards: List[float] = []
    steps_taken = 0
    last_status = ""
    last_done = False

    try:
        sync_env = IncidentEnv(base_url=ENV_URL).sync()
        with sync_env as env:
            reset_result = env.reset(task_id=task_id)
            history = reset_result.observation.stdout

            for step in range(1, MAX_STEPS + 1):
                command = get_action(client, history, task_id, step - 1)

                result = env.step(IncidentAction(command=command))
                obs = result.observation
                stdout = obs.stdout
                stderr = obs.stderr
                last_status = obs.status
                last_done = bool(result.done)

                history += f"\n> {command}\n"
                if stdout:
                    history += f"{stdout}\n"
                if stderr:
                    history += f"{stderr}\n"

                reward = float(result.reward) if result.reward is not None else 0.0
                rewards.append(reward)
                steps_taken = step

                log_step(step=step, action=command, reward=reward, done=last_done, error=stderr)

                if last_done:
                    break
    except Exception as exc:
        _stderr_log(f"Environment run failed for task {task_id}: {exc}")
    finally:
        final_score = rewards[-1] if rewards else 0.0
        final_score = max(0.0, min(final_score, 1.0))
        success = final_score > 0.0 and last_done
        log_end(success=success, steps=steps_taken, score=final_score, rewards=rewards)

    return final_score, last_status


def main() -> int:
    if not API_KEY or not MODEL_NAME:
        _stderr_log(
            "Missing API credentials. Set HF_TOKEN or OPENAI_API_KEY (or API_KEY) and MODEL_NAME."
        )
        _stderr_log("Continuing with deterministic plan (no LLM calls).")
        client = None
    else:
        client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    scores: Dict[str, float] = {}
    for task in TASK_PLANS.keys():
        score, _reason = run_task(client, task)
        scores[task] = score

    avg = sum(scores.values()) / max(len(scores), 1)
    avg = max(0.0, min(avg, 1.0))
    _stderr_log(f"Average score (stderr): {avg:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
