import json
import logging
import os


class Config:

    @staticmethod
    def parse(file_name: str):
        with open(file_name, "r") as file_json:
            try:
                return json.load(file_json)
            except ValueError as e:
                logging.error(f"Invalid json in {file_name}: {e}")
                raise e

    def __init__(self, file_name: str):
        self.options = self.parse(file_name)
        datapath = os.path.dirname(file_name)
        file_secrets = datapath + "/secrets.json"
        self.secrets = self.parse(file_secrets)

    def get(self, keys: list, options: dict = None, default=None) -> str | dict | list | None:
        if options is None:
            options = self.options
        if keys[0] in options:
            result = options[keys[0]]
            if str(result).lower().find("!secret", 0) == 0:
                result = self.secrets[result[8:]]
            if type(result) is dict:
                if len(keys) > 1:
                    result = self.get(keys[1:], result, default)
                else:
                    for key in result:
                        result[key] = self.get([key], result, default)
        else:
            result = default
        return result

    def set(self, key, value):
        self.options[key] = value


def get_config(file_name: str, keys: list, default=None):
    config = Config(file_name=file_name)
    return config.get(keys, None, default)
