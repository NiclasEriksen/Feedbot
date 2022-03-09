from googleapiclient import discovery
from googleapiclient.errors import UnknownApiNameOrVersion, HttpError
from google.auth.exceptions import DefaultCredentialsError
import logging

log = logging.getLogger("feedbot.google")
API_VERSION = "v1alpha1"


class GoogleError(Exception):
    pass



def create_factchect_service(api_key: str) -> discovery.Resource:
    try:
        service = discovery.build("factchecktools", API_VERSION, developerKey=api_key)
        return service.claims()
    except (UnknownApiNameOrVersion, HttpError, DefaultCredentialsError):
        raise GoogleError("Problem contacting fact-check API.")


if __name__ == "__main__":
    c = create_factchect_service("adasdasd")
    print(c)
