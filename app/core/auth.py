    
# Author: Rajasekhar Palleti
# QA

import requests

# Define constants for fixed values
GRANT_TYPE = "password"
CLIENT_ID = "resource_server"  # Replace with your actual client ID
CLIENT_SECRET = "resource_server"  # Replace with your actual client secret


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
        response = requests.post(auth_token_url, data=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors

        # Parse and return the access token
        return response.json().get("access_token")
    except Exception as e:
        print(f"Failed to retrieve access token: {e}")
        raise e
