import shutil
from urllib.error import HTTPError
from urllib.request import urlopen
import yaml
from yaml.loader import SafeLoader

# helper class for adding indentation while creating enviornment.yaml files got this solution from
# https://stackoverflow.com/a/39681672/12253398
class YamlDumper(yaml.Dumper):

    def increase_indent(self, flow=False, indentless=False):
        return super(YamlDumper, self).increase_indent(flow, False)

environment_file="https://github.com/ssurbhi560/condacolab/blob/07b92d827f56a4628a52f4f138ae92be3de5073d/environment.yaml",

try:
        with urlopen(environment_file) as response, open("environment.yaml", "wb") as out:
            shutil.copyfileobj(response, out)
except HTTPError as e:
        raise HTTPError(
            "The URL you entered is not working, please check it again."
        ) from e

with open('environment.yaml', 'r') as f:
    try:
        data = YamlDumper.load(f, Loader=SafeLoader) 
    except yaml.YAMLError as e:
        print(e)
print(data)