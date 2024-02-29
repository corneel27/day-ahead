import json
import os


class Config:

    def __init__(self, file_name: str):
        file_json = open(file_name)
        self.options = json.load(file_json)
        datapath = os.path.dirname(file_name)
        secrets_json = open(datapath + "/secrets.json")
        self.secrets = json.load(secrets_json)

    def get(self, keys:list, options=None, default=None) -> str|dict|list|None:
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


def get_config(file_name:str, keys:list, default=None):
    config = Config(file_name=file_name)
    return config.get(keys, None, default)
