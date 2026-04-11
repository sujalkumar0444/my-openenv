# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""Oncall Incident Response Environment Client."""

from typing import Dict

from openenv.core import EnvClient
from openenv.core.client_types import StepResult

from .models import IncidentAction, IncidentObservation, IncidentState


class IncidentEnv(
    EnvClient[IncidentAction, IncidentObservation, IncidentState]
):
    """
    Client for the Oncall Incident Response environment.

    This client maintains a persistent WebSocket connection to the environment server,
    enabling efficient multi-step interactions with lower latency.
    Each client instance has its own dedicated environment session on the server.

    Example:
        >>> # Connect to a running server
        >>> with IncidentEnv(base_url="http://localhost:8000") as client:
        ...     result = client.reset(task_id="restart_pod")
        ...     print(result.observation.stdout)
        ...
        ...     result = client.step(IncidentAction(command="status"))
        ...     print(result.observation.stdout)

    Example with Docker:
        >>> # Automatically start container and connect
        >>> client = IncidentEnv.from_docker_image("oncall-incident-env:latest")
        >>> try:
        ...     result = client.reset(task_id="restart_pod")
        ...     result = client.step(IncidentAction(command="status"))
        ... finally:
        ...     client.close()
    """

    def _step_payload(self, action: IncidentAction) -> Dict:
        """
        Convert IncidentAction to JSON payload for step message.

        Args:
            action: IncidentAction instance

        Returns:
            Dictionary representation suitable for JSON encoding
        """
        payload: Dict[str, object] = {
            "command": action.command,
        }
        if action.action_type:
            payload["action_type"] = action.action_type
        if action.service:
            payload["service"] = action.service
        if action.config_key:
            payload["config_key"] = action.config_key
        if action.config_value:
            payload["config_value"] = action.config_value
        return payload

    def _parse_result(self, payload: Dict) -> StepResult[IncidentObservation]:
        """
        Parse server response into StepResult[IncidentObservation].

        Args:
            payload: JSON response data from server

        Returns:
            StepResult with IncidentObservation
        """
        obs_data = payload.get("observation", {})
        observation = IncidentObservation(
            task_id=obs_data.get("task_id", ""),
            step_count=obs_data.get("step_count", 0),
            max_steps=obs_data.get("max_steps", 0),
            task_spec=obs_data.get("task_spec", {}),
            service_status=obs_data.get("service_status", {}),
            last_command=obs_data.get("last_command"),
            stdout=obs_data.get("stdout", ""),
            stderr=obs_data.get("stderr", ""),
            exit_code=obs_data.get("exit_code", 0),
            status=obs_data.get("status", ""),
            milestones=obs_data.get("milestones", {}),
            penalties=obs_data.get("penalties", {}),
            done=payload.get("done", False),
            reward=payload.get("reward"),
        )

        return StepResult(
            observation=observation,
            reward=payload.get("reward"),
            done=payload.get("done", False),
        )

    def _parse_state(self, payload: Dict) -> IncidentState:
        """
        Parse server response into State object.

        Args:
            payload: JSON response from state request

        Returns:
            State object with episode_id and step_count
        """
        return IncidentState(
            episode_id=payload.get("episode_id"),
            step_count=payload.get("step_count", 0),
            task_id=payload.get("task_id", ""),
            max_steps=payload.get("max_steps", 0),
            terminal_history=payload.get("terminal_history", ""),
            status=payload.get("status", ""),
            completed=payload.get("completed", False),
            score=payload.get("score", 0.0),
            task_spec=payload.get("task_spec", {}),
            service_status=payload.get("service_status", {}),
            scenario=payload.get("scenario", {}),
            config_state=payload.get("config_state", {}),
            milestones=payload.get("milestones", {}),
            penalties=payload.get("penalties", {}),
            last_command=payload.get("last_command"),
        )
