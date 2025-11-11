# Standard library imports
import os

# Third-party imports
import requests
from requests.auth import HTTPBasicAuth


def notify_pipeline(message: str = "ready") -> None:
    """
    Send callback by updating Jenkins build description via REST API

    Environment variables required: (supplied by jenkins)
    - JENKINS_URL: Jenkins base URL
    - JENKINS_USER: Jenkins username
    - JENKINS_TOKEN: Jenkins API token
    - JENKINS_JOB: Job name (e.g., "run-app")
    - JENKINS_BUILD_NUMBER: Build number
    - PIPELINE_CALLBACK_TOKEN: Unique token for this build
    - PIPELINE_CALLBACK_SECRET: Shared secret (optional validation)
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