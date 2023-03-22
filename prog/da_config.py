import json


class Config:

    def __init__(self, file_name):
        if file_name is None:
            file_json = open(file_name)
        else:
            file_json = open(file_name)
        self.options = json.load(file_json)
        secrets_json = open("../data/secrets.json")
        self.secrets = json.load(secrets_json)

    def get (self, keys, options = None):
        if options is None:
            options = self.options
        result = options[keys[0]]
        if str(result).lower().find("!secret", 0) == 0:
            result = self.secrets[result[8:]]
        if type(result) is dict:
            if len(keys)>1:
                result = self.get(keys[1:], result)
            else:
                for key in result:
                    result[key] = self.get([key], result)
        return result

    def set(self, key, value):
        self.options[key] = value
