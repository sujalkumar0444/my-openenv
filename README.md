---
title: Oncall Incident Response OpenEnv
emoji: ☁️
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8000
base_path: /web
tags: [openenv]
---

# Oncall Incident Response OpenEnv

An OpenEnv environment simulating real-world on-call incident response for a SaaS platform. Agents use a CLI to inspect status, read logs, fix configuration, and safely roll back deployments.

## Motivation & Utility
Production incidents require careful investigation, safe remediation, and disciplined change management. This environment is designed to help agents practice those workflows with deterministic grading and partial credit for correct investigative steps.

## Observation Space
- `stdout` (string): Standard output from the mock CLI commands.
- `stderr` (string): Standard error output.
- `exit_code` (int): 0 for success, non-zero for failures.
- `status` (string): Progress or grading status message.
- `milestones` (dict): Completed milestones for the active task.
- `penalties` (dict): Penalty counters for invalid or repeated actions.

## Action Space
- `command` (string): The single CLI command to run.
  - Supported commands: `status`, `logs <service>`, `restart <service>`, `edit_config <service> <key=value>`, `drain <service>`, `rollback <service>`, `help`, `noop`

## Reward Function
- Partial progress rewards for investigation and safe remediation steps.
- Penalties for invalid or repeated commands.
- Critical failure (score 0.0) if a rollback is attempted while traffic is still active.

## Tasks & Difficulty
1. **restart_pod (Easy)**
   - *Objective:* Inspect status and logs, then restart `payments-db`.
   - *Grading:* Credit for investigation and full score for successful restart.
2. **fix_config (Medium)**
   - *Objective:* Identify the bad DB host in `checkout-api` logs, update `DATABASE_HOST`, and restart the service.
   - *Grading:* Partial rewards for status/log review, full score after config fix + restart.
3. **rollback_deploy (Hard)**
   - *Objective:* Confirm memory leak, drain traffic from `search-api`, then roll back safely.
   - *Grading:* Partial rewards for investigation and draining, full score for safe rollback.

## Setup & Usage

### Running Locally (UV)
```bash
uv sync
uv run server
```

### Running Locally (Docker)
```bash
docker build -t oncall-incident-env -f server/Dockerfile .
docker run -p 8000:8000 oncall-incident-env
```

## OpenEnv Endpoints
- `POST /reset` with `{ "task_id": "..." }`
- `POST /step` with `{ "action": { "command": "..." } }`
- `GET /state`
- `GET /health`
- `GET /metadata`
- `GET /schema`
- `POST /mcp`

## Validation
Run the OpenEnv validator before submission:
```bash
openenv validate --url http://127.0.0.1:8000
```

## Inference Baseline
The repository includes a baseline `inference.py` script that uses the OpenAI client.

Required environment variables:
- `API_BASE_URL` (example: `https://router.huggingface.co/v1`)
- `MODEL_NAME`
- `HF_TOKEN` (or `OPENAI_API_KEY`)

```bash
export API_BASE_URL="https://router.huggingface.co/v1"
export MODEL_NAME="your-model"
export HF_TOKEN="your-api-key"
python inference.py
```

Baseline scores are deterministic because the script uses a fixed task plan with an LLM-constrained fallback.

### Baseline Scores (Deterministic Plan)
- `restart_pod`: 1.0
- `fix_config`: 1.0
- `rollback_deploy`: 1.0
- Average: 1.0

## Deploy to Hugging Face Spaces
1. Create a new Space with **SDK = Docker** and set `app_port` to `8000`.
2. Push this repository to the Space.
3. Add Space secrets for `API_BASE_URL`, `MODEL_NAME`, and `HF_TOKEN` (or `OPENAI_API_KEY`).
4. Wait for the Space build to complete, then verify `/reset` and `/state` respond with HTTP 200.

You can also deploy with the OpenEnv CLI:
```bash
openenv push --repo-id your-username/oncall-incident-response
```
