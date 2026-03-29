# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree.

"""
Data models for the Oncall Incident Response environment.
"""

from typing import Dict, Optional

from openenv.core.env_server.types import Action, Observation, State
from pydantic import Field


class IncidentAction(Action):
    """Action for the incident response environment."""

    command: str = Field(..., description="CLI command to execute")


class IncidentObservation(Observation):
    """Observation returned by the incident response environment."""

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
    milestones: Dict[str, bool] = Field(
        default_factory=dict,
        description="Milestones achieved so far",
    )
    penalties: Dict[str, int] = Field(
        default_factory=dict,
        description="Penalty counters so far",
    )
    last_command: Optional[str] = Field(default=None, description="Most recent command")
