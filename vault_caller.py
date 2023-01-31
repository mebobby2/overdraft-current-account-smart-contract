import functools
import json
import requests
from collections import namedtuple


class VaultException(Exception):
    def __init__(self, vault_error_code, message):
        self.vault_error_code = vault_error_code
        self.message = message

    def __str__(self):
        return "An exception was raised inside Vault:\nError Code: %s\nMessage:\n%s" % (
            self.vault_error_code,
            self.message,
        )


def _auth_required(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        return func(self, *args, **kwargs)

    return wrapper


SimulationInstruction = namedtuple(
    "SimulationInstruction", ["time", "instruction"])


class Client:
    def __init__(self, *, core_api_url, auth_token):
        self._core_api_url = core_api_url.rstrip("/")
        self._auth_token = auth_token

    @_auth_required
    def _api_post(self, url, payload, timeout):
        response = requests.post(
            self._core_api_url + url,
            headers={
                "Content-Type": "application/json",
                "X-Auth-Token": self._auth_token,
                "grpc-timeout": timeout,
            },
            json=payload,
            stream=True,
        )

        resp = []
        for line in response.iter_lines():
            json_line = json.loads(line)
            self._handle_error(json_line)

            resp.append(json_line)

        return resp

    @staticmethod
    def _handle_error(content):
        if "vault_error_code" in content and "message" in content:
            raise VaultException(
                content["vault_error_code"], content["message"])
        if "error" in content:
            raise ValueError(content["error"])

    def simulate_contracts(
        self, *, smart_contracts, start_timestamp, end_timestamp, instructions, timeout="10S"
    ):
        instructions = [_instruction_to_json(
            instruction) for instruction in instructions]
        payload = self._api_post(
            "/v1/contracts:simulate",
            {
                "smart_contracts": smart_contracts,
                "start_timestamp": _datetime_to_rfc_3339(start_timestamp),
                "end_timestamp": _datetime_to_rfc_3339(end_timestamp),
                "instructions": instructions,
            },
            timeout=timeout,
        )
        return payload


def _datetime_to_rfc_3339(dt):
    timezone_aware = dt.tzinfo is not None and dt.tzinfo.utcoffset(
        dt) is not None
    if not timezone_aware:
        raise ValueError("The datetime object passed in is not timezone-aware")
    return dt.astimezone().isoformat()


def _instruction_to_json(instruction):
    return {"timestamp": _datetime_to_rfc_3339(instruction.time), **instruction.instruction}
