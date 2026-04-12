# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the Oncall Incident Response environment.
"""

from typing import Any, Dict, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class IncidentAction(Action):
    """Action for the incident response environment."""

    command: str = Field(default="", description="CLI command to execute")
    action_type: Optional[str] = Field(
        default=None,
        description="Structured action type (status, logs, restart, edit_config, drain, rollback, help, noop)",
    )
    service: Optional[str] = Field(
        default=None, description="Target service for structured actions"
    )
    config_key: Optional[str] = Field(
        default=None, description="Config key for edit_config actions"
    )
    config_value: Optional[str] = Field(
        default=None, description="Config value for edit_config actions"
    )


class IncidentObservation(Observation):
    """Observation returned by the incident response environment."""

    task_id: str = Field(default="", description="Active task identifier")
    step_count: int = Field(default=0, description="Current step count")
    max_steps: int = Field(default=0, description="Maximum steps for this task")
    task_spec: Dict[str, Any] = Field(
        default_factory=dict,
        description="Task metadata including objective and difficulty",
    )
    service_status: Dict[str, str] = Field(
        default_factory=dict,
        description="Latest status for each service",
    )
    service_versions: Dict[str, str] = Field(
        default_factory=dict,
        description="Service version map for the active task",
    )
    incident: Dict[str, Any] = Field(
        default_factory=dict,
        description="Incident metadata (id, severity, impact, variant)",
    )
    alerts: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="Active alert list with acknowledgement status",
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Latest metrics snapshot for services",
    )
    timeline: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="Incident timeline events",
    )
    config_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="Config state for tasks that require edits",
    )
    last_command: Optional[str] = Field(
        default=None, description="Most recent command executed"
    )
    stdout: str = Field(default="", description="Standard output from the CLI command")
    stderr: str = Field(default="", description="Standard error from the CLI command")
    exit_code: int = Field(default=0, description="Exit code from the CLI command")
    status: str = Field(default="", description="Progress or grading status message")
    milestones: Dict[str, bool] = Field(
        default_factory=dict,
        description="Completed milestones for the active task",
    )
    penalties: Dict[str, int] = Field(
        default_factory=dict,
        description="Penalty counters for invalid or repeated actions",
    )


class IncidentState(State):
    """State for the incident response environment."""

    task_id: str = Field(default="", description="Active task identifier")
    max_steps: int = Field(default=0, description="Maximum steps for the current task")
    terminal_history: str = Field(default="", description="Command history")
    status: str = Field(default="", description="Current grading status")
    completed: bool = Field(default=False, description="Whether the task is complete")
    score: float = Field(default=0.0, description="Current score for the task")
    task_spec: Dict[str, Any] = Field(
        default_factory=dict,
        description="Task metadata including objective and difficulty",
    )
    service_status: Dict[str, str] = Field(
        default_factory=dict,
        description="Latest status for each service",
    )
    scenario: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scenario configuration for the active task",
    )
    config_state: Dict[str, Any] = Field(
        default_factory=dict,
        description="Config state for tasks that require edits",
    )
    service_versions: Dict[str, str] = Field(
        default_factory=dict,
        description="Service version map for the active task",
    )
    incident: Dict[str, Any] = Field(
        default_factory=dict,
        description="Incident metadata (id, severity, impact, variant)",
    )
    alerts: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="Active alert list with acknowledgement status",
    )
    metrics: Dict[str, Any] = Field(
        default_factory=dict,
        description="Latest metrics snapshot for services",
    )
    timeline: list[Dict[str, Any]] = Field(
        default_factory=list,
        description="Incident timeline events",
    )
    milestones: Dict[str, bool] = Field(
        default_factory=dict,
        description="Milestones achieved so far",
    )
    penalties: Dict[str, int] = Field(
        default_factory=dict,
        description="Penalty counters so far",
    )
    last_command: Optional[str] = Field(default=None, description="Most recent command")
