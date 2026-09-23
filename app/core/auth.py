    
# Author: Rajasekhar Palleti
# QA

import requests

# Define constants for fixed values
GRANT_TYPE = "password"
CLIENT_ID = "resource_server"  # Replace with your actual client ID
CLIENT_SECRET = "resource_server"  # Replace with your actual client secret

AUTH_TIMEOUT = 30  # seconds — prevents hanging forever on slow SSO on Render/cloud


def get_access_token(tenant_code, username, password, environment):
    """Fetch the access token using the tenant_code, username, password and environment.

    Args:
        tenant_code (str): The tenant code for the authentication.
        username (str): The username for the authentication.
        password (str): The password for the authentication.
        environment (str): The environment to use for authentication. Defaults to "prod1".
                          Can be "prod1" or "prod2".

    Returns:
        str: The access token if successful, otherwise None.
    """
    try:
        # Define the payload for the POST request
        payload = {
            "username": username,
            "password": password,
            "grant_type": GRANT_TYPE,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        }

        # Determine the authentication URL based on the environment
        SSO_BASES = {
            "prod1": "https://sso.sg.cropin.in",
            "prod2": "https://sso.africa.cropin.com",
            "qa":    "https://v2sso-gcp.cropin.co.in",
            "uat":   "https://v2sso-uat-gcp.cropin.co.in",
        }
        if environment not in SSO_BASES:
            raise ValueError(f"Invalid environment '{environment}'. Use one of: {', '.join(SSO_BASES)}.")
        auth_token_url = f"{SSO_BASES[environment]}/auth/realms/{tenant_code}/protocol/openid-connect/token"

        # Send the POST request with x-www-form-urlencoded data
        # timeout prevents hanging forever on slow SSO (critical on Render/cloud deployments)
        response = requests.post(auth_token_url, data=payload, timeout=AUTH_TIMEOUT)

        if response.status_code == 401:
            raise Exception("Invalid username or password (HTTP 401 Unauthorized).")
        if response.status_code == 400:
            body = response.json()
            raise Exception(f"Bad request to SSO: {body.get('error_description', response.text)}")

        response.raise_for_status()  # Raise an exception for other HTTP errors

        token = response.json().get("access_token")
        if not token:
            raise Exception("SSO response did not contain an access_token.")
        return token
    except requests.exceptions.Timeout:
        raise Exception(f"Authentication timed out after {AUTH_TIMEOUT}s. SSO server may be slow or unreachable.")
    except requests.exceptions.ConnectionError as ce:
        raise Exception(f"Cannot reach SSO server: {ce}")
    except Exception as e:
        print(f"Failed to retrieve access token: {e}")
        raise e
