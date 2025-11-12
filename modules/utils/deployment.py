"""Jenkins CI/CD pipeline integration for deployment callbacks.

This module provides utilities for Desktop Agent to communicate back to
Jenkins CI/CD pipelines during automated deployments. It allows the agent
to signal readiness or completion status to the orchestrating pipeline.

The primary use case is for automated testing and deployment workflows where
Jenkins launches the Desktop Agent in a test environment, waits for it to
initialize, and then proceeds with further testing or validation steps.

Communication Protocol:
    The agent updates its Jenkins build description with a special callback
    marker that the pipeline can poll for. Format: "✓ CALLBACK:{token}:{message}"

Environment Variables Required:
    These are typically set automatically by Jenkins when launching the agent:
    - JENKINS_URL: Jenkins base URL (e.g., "https://jenkins.example.com")
    - JENKINS_USER: Jenkins username for API authentication
    - JENKINS_TOKEN: Jenkins API token for authentication
    - JENKINS_JOB: Job name (e.g., "desktop-agent-test")
    - JENKINS_BUILD_NUMBER: Current build number
    - PIPELINE_CALLBACK_TOKEN: Unique token for this build (prevents conflicts)
    - PIPELINE_CALLBACK_SECRET: Optional shared secret for validation

Example:
    >>> import os
    >>> from modules.utils.deployment import notify_pipeline
    >>>
    >>> # Set up environment (normally done by Jenkins)
    >>> os.environ['JENKINS_URL'] = 'https://jenkins.example.com'
    >>> os.environ['JENKINS_USER'] = 'automation'
    >>> os.environ['JENKINS_TOKEN'] = 'api_token_here'
    >>> os.environ['JENKINS_JOB'] = 'desktop-agent-test'
    >>> os.environ['JENKINS_BUILD_NUMBER'] = '42'
    >>> os.environ['PIPELINE_CALLBACK_TOKEN'] = 'abc123'
    >>>
    >>> # Notify pipeline that agent is ready
    >>> notify_pipeline("ready")
    'Sending callback to Jenkins build desktop-agent-test #42'
    '✓ Callback sent successfully (status: 200)'
"""

# Standard library imports
import os

# Third-party imports
import requests
from requests.auth import HTTPBasicAuth


def notify_pipeline(message: str = "ready") -> None:
    """Send callback to Jenkins pipeline by updating build description.

    Communicates with the orchestrating Jenkins pipeline by updating the
    current build's description with a special callback marker. The pipeline
    polls this description to detect when the agent reaches specific states.

    Args:
        message: Status message to send (default: "ready"). Common values:
            - "ready": Agent initialized and ready for testing
            - "complete": Agent finished processing
            - "error": Agent encountered an error
            Custom messages are also supported.

    Raises:
        ValueError: If required environment variables are missing.
        requests.RequestException: If Jenkins API request fails.

    Example:
        >>> # Signal that agent is ready
        >>> notify_pipeline("ready")

        >>> # Signal completion
        >>> notify_pipeline("complete")

        >>> # Signal custom state
        >>> notify_pipeline("mqtt_connected")
    """

    jenkins_url = os.environ.get("JENKINS_URL", "").rstrip("/")
    jenkins_user = os.environ.get("JENKINS_USER")
    jenkins_token = os.environ.get("JENKINS_TOKEN")
    job_name = os.environ.get("JENKINS_JOB")
    build_number = os.environ.get("JENKINS_BUILD_NUMBER")
    callback_token = os.environ.get("PIPELINE_CALLBACK_TOKEN")

    if not all([jenkins_url, jenkins_user, jenkins_token, job_name, build_number, callback_token]):
        raise ValueError(
            "Missing required environment variables: "
            "JENKINS_URL, JENKINS_USER, JENKINS_TOKEN, JENKINS_JOB, "
            "JENKINS_BUILD_NUMBER, PIPELINE_CALLBACK_TOKEN"
        )

    # Construct API endpoint to update build description
    # Format: {JENKINS_URL}/job/{JOB_NAME}/{BUILD_NUMBER}/submitDescription
    api_url = f"{jenkins_url}/job/{job_name}/{build_number}/submitDescription"

    # Prepare callback data in build description
    # Format: "✓ CALLBACK: {token}: {message}"
    description = f"✓ CALLBACK:{callback_token}:{message}"

    # Prepare form data (Jenkins expects 'description' field)
    data = {
        "description": description,
        "Submit": "Submit"  # Jenkins form requirement
    }

    try:
        print(f"Sending callback to Jenkins build {job_name} #{build_number}")

        response = requests.post(
            api_url,
            data=data,
            auth=HTTPBasicAuth(jenkins_user, jenkins_token),
            timeout=30,
            # For homelab with self-signed certs
            verify=os.environ.get("VERIFY_SSL", "true").lower() != "false"
        )

        response.raise_for_status()
        print(f"✓ Callback sent successfully (status: {response.status_code})")

    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to send callback: {e}")
        raise