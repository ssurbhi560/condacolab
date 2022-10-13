from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

yaml=YAML()
yaml.indent(mapping=2, sequence=4, offset=2)

python_version = "3.9"

specs = ["flask", "matplotlib", "numpy"]
pip_args = ["flask-wtf", "graphql"]
channels = ["bioconda"]
extra_conda_args = ["-yq"]
environment_file_url = "https://raw.githubusercontent.com/ssurbhi560/condacolab/07b92d827f56a4628a52f4f138ae92be3de5073d/environment.yaml"
env_details = {"channels" : ["conda-forge", "bioconda"], "specs": ["flask", "flask-sqlalchemy", "curl", {"pip" : ["pyyaml"]}]}

with open("env.yaml", 'r') as f:
    data = yaml.load(f.read())

    # print(type(data) == ruamel.yaml.comments.CommentedMap)
    for key in data:
        # print(data["dependencies"]) > ['flask', 'flask-sqlalchemy', 'curl', ordereddict([('pip', ['pyyaml'])])]
        if channels and key == "channels":
            data["channels"] += channels
        if key == "dependencies":
            if specs:
                data["dependencies"] += specs
            if python_version:
                data["dependencies"] += [f"python={python_version}"]
            if pip_args:
                for element in data["dependencies"]:
                    if type(element) is CommentedMap and "pip" in element:
                        element["pip"] += pip_args
                    else : 
                        pip_args_dict = CommentedMap([("pip", [*pip_args])])
                        data["dependencies"].append(pip_args_dict)
# fix this.
                    break

print(data)
with open("env.yaml", 'w') as f:
    f.truncate(0)
    yaml.dump(data, f)




