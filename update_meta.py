import requests
import yaml
import re

# Fetch the latest version from PyPI
response = requests.get('https://pypi.org/pypi/calibrated-explanations/json')
data = response.json()
latest_version = data['info']['version']
sha256_url = f"https://pypi.org/project/calibrated-explanations/{latest_version}/#files"
sha256_response = requests.get(sha256_url)
sha256_match = re.search(r'sha256=([a-f0-9]{64})', sha256_response.text)
latest_sha256 = sha256_match.group(1) if sha256_match else None

if not latest_sha256:
    raise ValueError("Could not find sha256 hash on PyPI page")

# Read the existing meta.yaml file
with open('meta.yaml', 'r') as file:
    meta = yaml.safe_load(file)

# Update the version and sha256
meta['package']['version'] = latest_version
meta['source']['url'] = f"https://pypi.io/packages/source/c/calibrated-explanations/calibrated_explanations-{latest_version}.tar.gz"
meta['source']['sha256'] = latest_sha256

# Write the updated meta.yaml file
with open('meta.yaml', 'w') as file:
    yaml.dump(meta, file, default_flow_style=False)