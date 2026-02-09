import requests
import logging

logger = logging.getLogger(__name__)


def login(base_url_lovin, username, password):
    query = """
    mutation LoginUser {
      login( input: {
        clientMutationId: "uniqueId",
        username: "%s",
        password: "%s"
      } ) {
        authToken
        user { id name }
      }
    }
    """ % (username, password)
    headers = {"Content-Type": "application/json"}
    response = requests.post(base_url_lovin, json={"query": query}, headers=headers)
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise Exception(f"Login failed: {str(data['errors'])}")
    auth_token = data["data"]["login"]["authToken"]
    logger.info("Lovin login successful")
    return auth_token