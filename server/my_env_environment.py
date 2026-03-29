# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Oncall Incident Response Environment Implementation.
"""

from uuid import uuid4
from typing import Any, Dict, Optional, Tuple

from openenv.core.env_server.interfaces import Environment
from openenv.core.env_server.types import EnvironmentMetadata

try:
    from ..models import IncidentAction, IncidentObservation, IncidentState
except ImportError:
    from models import IncidentAction, IncidentObservation, IncidentState


TASK_SPECS: Dict[str, Dict[str, Any]] = {
    "restart_pod": {
        "title": "Recover crash-looping database",
        "difficulty": "easy",
        "objective": "Inspect status and logs, then restart payments-db to restore service.",
        "max_steps": 10,
        "services": ["payments-db", "payments-api"],
        "primary_service": "payments-db",
        "log_message": "FATAL: database process exited unexpectedly. CrashLoopBackOff triggered.",
        "success_reason": "Payments database restarted and service stabilized.",
    },
    "fix_config": {
        "title": "Fix DB host misconfiguration",
        "difficulty": "medium",
        "objective": "Find the bad DB host in checkout-api logs, fix DATABASE_HOST, and restart.",
        "max_steps": 12,
        "services": ["checkout-api", "checkout-worker"],
        "primary_service": "checkout-api",
        "log_message": "ERROR: connection failed (host=db-prod.local invalid).",
        "config_key": "DATABASE_HOST",
        "config_value": "db-prod.internal",
        "success_reason": "Checkout API config fixed and service restarted with healthy DB connection.",
    },
    "rollback_deploy": {
        "title": "Rollback a leaky deployment safely",
        "difficulty": "hard",
        "objective": "Confirm memory leak in logs, drain traffic, then rollback search-api.",
        "max_steps": 14,
        "services": ["search-api", "search-indexer"],
        "primary_service": "search-api",
        "log_message": "OutOfMemoryError: heap usage exceeded after build 2.3.1.",
        "success_reason": "Traffic drained and search API rolled back to stable build.",
    },
}

HELP_TEXT = (
    "Commands: status, logs <service>, restart <service>, edit_config <service> <key=value>, "
    "drain <service>, rollback <service>, help, noop"
)


class IncidentResponseEnvironment(Environment[IncidentAction, IncidentObservation, IncidentState]):
    """Incident response environment for on-call workflows."""

    SUPPORTS_CONCURRENT_SESSIONS: bool = True

    def __init__(self):
        super().__init__()
        self._task_id = ""
        self._episode_id: Optional[str] = None
        self.step_count = 0
        self.max_steps = 12
        self.tasks = list(TASK_SPECS.keys())
        self._state: Dict[str, Any] = {}
        self._reset_state()

    def _reset_state(self) -> None:
        self._state = {
            "checked_status": False,
            "checked_logs": False,
            "restarted": False,
            "config_fixed": False,
            "drained": False,
            "rolled_back": False,
            "invalid_actions": 0,
            "repeat_actions": 0,
            "unsafe_action": False,
            "last_command": None,
            "history": [],
        }

    def reset(
        self,
        seed: Optional[int] = None,
        episode_id: Optional[str] = None,
        **kwargs: Any,
    ) -> IncidentObservation:
        task_id = kwargs.get("task_id") or (self.tasks[0] if self.tasks else "")
        if task_id not in TASK_SPECS:
            raise ValueError(f"Task {task_id} not found. Must be one of {self.tasks}.")

        self._task_id = task_id
        self.step_count = 0
        self.max_steps = TASK_SPECS[task_id]["max_steps"]
        self._episode_id = episode_id or str(uuid4())
        self._reset_state()

        spec = TASK_SPECS[task_id]
        banner = (
            "Oncall Incident Console\n"
            f"Task: {task_id} ({spec['difficulty']})\n"
            f"Objective: {spec['objective']}\n"
            f"Services: {', '.join(spec['services'])}\n"
            "Type 'help' for available commands."
        )

        milestones = self._milestones()
        penalties = self._penalties()

        return IncidentObservation(
            stdout=banner,
            stderr="",
            exit_code=0,
            status="Task initialized.",
            milestones=milestones,
            penalties=penalties,
            reward=None,
            done=False,
        )

    def _record_command(self, command: str) -> str:
        normalized = " ".join(command.strip().split())
        last = self._state.get("last_command")
        if normalized and last == normalized.lower():
            self._state["repeat_actions"] += 1
        self._state["last_command"] = normalized.lower() if normalized else None
        self._state["history"].append(command)
        return normalized

    def _status_output(self) -> str:
        if self._task_id == "restart_pod":
            if self._state["restarted"]:
                db_status = "payments-db: Healthy (uptime 2m)"
            else:
                db_status = "payments-db: CrashLoopBackOff (restart count 12)"
            return f"{db_status}\npayments-api: Healthy"

        if self._task_id == "fix_config":
            if self._state["restarted"] and self._state["config_fixed"]:
                api_status = "checkout-api: Healthy (db connected)"
            elif self._state["config_fixed"]:
                api_status = "checkout-api: Restarting after config update"
            else:
                api_status = "checkout-api: Error (DB connection refused)"
            return f"{api_status}\ncheckout-worker: Healthy"

        if self._task_id == "rollback_deploy":
            traffic = "drained" if self._state["drained"] else "active"
            if self._state["rolled_back"]:
                api_status = "search-api: Healthy (version 2.3.0)"
            else:
                api_status = "search-api: High Memory Usage (version 2.3.1)"
            return f"{api_status} | traffic: {traffic}\nsearch-indexer: Healthy"

        return "No active task."

    def _logs_output(self, target: str) -> Tuple[str, str, int]:
        spec = TASK_SPECS[self._task_id]
        if target not in spec["services"]:
            return "", f"Service '{target}' not found.", 1
        if target == spec["primary_service"]:
            self._state["checked_logs"] = True
            return spec["log_message"], "", 0
        return f"{target}: no recent errors in last 15m.", "", 0

    def _execute(self, command: str) -> Tuple[str, str, int]:
        normalized = self._record_command(command)
        if not normalized:
            return "", "Empty command", 1

        parts = normalized.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if not self._task_id and cmd not in {"help", "noop"}:
            return "", "No task loaded. Call reset first.", 1

        if cmd == "help":
            return HELP_TEXT, "", 0

        if cmd == "noop":
            return "No-op.", "", 0

        if cmd == "status":
            self._state["checked_status"] = True
            return self._status_output(), "", 0

        if cmd == "logs":
            if not args:
                return "", "Missing service name", 1
            target = args[0].lower()
            return self._logs_output(target)

        if cmd == "restart":
            if not args:
                return "", "Missing service name", 1
            target = args[0].lower()
            spec = TASK_SPECS[self._task_id]
            if target not in spec["services"]:
                return "", f"Service '{target}' not found.", 1
            if self._task_id == "restart_pod" and target == spec["primary_service"]:
                self._state["restarted"] = True
                return f"Restarting {target}... Done.", "", 0
            if self._task_id == "fix_config" and target == spec["primary_service"]:
                if not self._state["config_fixed"]:
                    return "", "Config is still invalid. Update config before restart.", 1
                self._state["restarted"] = True
                return f"Restarting {target} with updated config... Done.", "", 0
            return "", "Restart is not required for this task.", 1

        if cmd == "edit_config":
            if len(args) < 2:
                return "", "Usage: edit_config <service> <key=value>", 1
            target = args[0].lower()
            kv = args[1]
            if "=" not in kv:
                return "", "Config must be key=value.", 1
            key, value = kv.split("=", 1)
            key = key.strip().upper()
            value = value.strip()
            spec = TASK_SPECS[self._task_id]
            if self._task_id != "fix_config":
                return "", "Config edits are not allowed for this task.", 1
            if target != spec["primary_service"]:
                return "", f"Service '{target}' does not accept config changes here.", 1
            if key != spec["config_key"]:
                return "", f"Expected key {spec['config_key']}.", 1
            if value != spec["config_value"]:
                return "", "Config value rejected by validation.", 1
            self._state["config_fixed"] = True
            return "Config updated. Restart required.", "", 0

        if cmd == "drain":
            if not args:
                return "", "Missing service name", 1
            target = args[0].lower()
            spec = TASK_SPECS[self._task_id]
            if self._task_id != "rollback_deploy":
                return "", "Drain is only used for rollback tasks.", 1
            if target != spec["primary_service"]:
                return "", f"Service '{target}' cannot be drained here.", 1
            self._state["drained"] = True
            return f"Traffic drained from {target}.", "", 0

        if cmd == "rollback":
            if not args:
                return "", "Missing service name", 1
            target = args[0].lower()
            spec = TASK_SPECS[self._task_id]
            if self._task_id != "rollback_deploy":
                return "", "Rollback is only used for rollback tasks.", 1
            if target != spec["primary_service"]:
                return "", f"Service '{target}' cannot be rolled back here.", 1
            if not self._state["drained"]:
                self._state["unsafe_action"] = True
                return "", "Unsafe rollback: traffic still active. Incident escalated.", 1
            self._state["rolled_back"] = True
            return f"Rolled back {target} to version 2.3.0.", "", 0

        return "", f"Command '{cmd}' not found", 127

    def _milestones(self) -> Dict[str, bool]:
        if self._task_id == "restart_pod":
            return {
                "checked_status": self._state["checked_status"],
                "checked_logs": self._state["checked_logs"],
                "restarted": self._state["restarted"],
            }
        if self._task_id == "fix_config":
            return {
                "checked_status": self._state["checked_status"],
                "checked_logs": self._state["checked_logs"],
                "config_fixed": self._state["config_fixed"],
                "restarted": self._state["restarted"],
            }
        if self._task_id == "rollback_deploy":
            return {
                "checked_logs": self._state["checked_logs"],
                "drained": self._state["drained"],
                "rolled_back": self._state["rolled_back"],
            }
        return {}

    def _base_score(self, milestones: Dict[str, bool]) -> Tuple[float, bool, str]:
        if self._task_id == "restart_pod":
            score = 0.0
            if milestones.get("checked_status"):
                score += 0.2
            if milestones.get("checked_logs"):
                score += 0.2
            if milestones.get("restarted"):
                score += 0.6
            return score, milestones.get("restarted", False), TASK_SPECS[self._task_id][
                "success_reason"
            ]

        if self._task_id == "fix_config":
            score = 0.0
            if milestones.get("checked_status"):
                score += 0.15
            if milestones.get("checked_logs"):
                score += 0.25
            if milestones.get("config_fixed"):
                score += 0.35
            if milestones.get("restarted"):
                score += 0.25
            success = milestones.get("config_fixed", False) and milestones.get(
                "restarted", False
            )
            return score, success, TASK_SPECS[self._task_id]["success_reason"]

        if self._task_id == "rollback_deploy":
            score = 0.0
            if milestones.get("checked_logs"):
                score += 0.15
            if milestones.get("drained"):
                score += 0.35
            if milestones.get("rolled_back"):
                score += 0.5
            success = milestones.get("rolled_back", False) and milestones.get(
                "drained", False
            )
            return score, success, TASK_SPECS[self._task_id]["success_reason"]

        return 0.0, False, ""

    def _penalty_value(self) -> float:
        invalid_penalty = min(self._state["invalid_actions"] * 0.05, 0.25)
        repeat_penalty = min(self._state["repeat_actions"] * 0.03, 0.15)
        return invalid_penalty + repeat_penalty

    def _penalties(self) -> Dict[str, int]:
        return {
            "invalid_actions": int(self._state["invalid_actions"]),
            "repeat_actions": int(self._state["repeat_actions"]),
        }

    def _progress_reason(
        self, milestones: Dict[str, bool], penalties: Dict[str, int]
    ) -> str:
        completed = [key for key, value in milestones.items() if value]
        progress = ", ".join(completed) if completed else "none"
        return (
            f"Progress: {progress}. "
            f"Penalties: invalid={penalties['invalid_actions']}, repeat={penalties['repeat_actions']}.")

    def _grade(self) -> Tuple[float, str, bool, Dict[str, bool], Dict[str, int]]:
        penalties = self._penalties()
        if not self._task_id:
            return 0.0, "No task loaded.", False, {}, penalties

        milestones = self._milestones()
        base_score, success, success_reason = self._base_score(milestones)
        score = max(0.0, min(1.0, base_score - self._penalty_value()))

        if self._state["unsafe_action"]:
            return 0.0, "Critical failure: rolled back while traffic was active.", True, milestones, penalties

        if success:
            return score, success_reason, True, milestones, penalties

        done = False
        reason = self._progress_reason(milestones, penalties)
        if self.step_count >= self.max_steps:
            done = True
            reason = f"Max steps reached. {reason}"

        return score, reason, done, milestones, penalties

    def step(
        self, action: IncidentAction, timeout_s: Optional[float] = None, **kwargs: Any
    ) -> IncidentObservation:  # type: ignore[override]
        self.step_count += 1

        out, err, code = self._execute(action.command)
        if code != 0:
            self._state["invalid_actions"] += 1

        score, reason, done, milestones, penalties = self._grade()

        return IncidentObservation(
            stdout=out,
            stderr=err,
            exit_code=code,
            status=reason,
            milestones=milestones,
            penalties=penalties,
            reward=score,
            done=done,
        )

    @property
    def state(self) -> IncidentState:
        score, reason, done, milestones, penalties = self._grade()
        hist = "\n".join(self._state.get("history", []))
        return IncidentState(
            episode_id=self._episode_id,
            step_count=self.step_count,
            task_id=self._task_id or "",
            max_steps=self.max_steps,
            terminal_history=hist,
            status=reason,
            completed=done,
            score=score,
            milestones=milestones,
            penalties=penalties,
            last_command=self._state.get("last_command"),
        )

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name="Oncall Incident Response",
            description=(
                "A real-world incident response environment for on-call reliability tasks."
            ),
            version="1.1.0",
        )

    def close(self) -> None:
        return None
