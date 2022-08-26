# "{activator}"
# "{bin_path}/python3"

import json

with open("kernell.json", 'r') as f:
    data = json.load(f)
    
## Working with buffered content
if data["argv"][0] != "somethingg/bin/python3":
    
    data["argv"][0] = "somethingg/bin/python3"
    data["display_name"] = "Python 3 (condacolab)"
    data["argv"].insert(1, "somethinggggggg/bin/something")


    with open("kernell.json", "w+") as f:
        f.write(json.dumps(data))




# you have a list and you want to add at 0 position a string and at 1 postion another string. along with that you also want 
# this to happen only once