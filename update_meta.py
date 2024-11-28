import requests
import re

# Fetch the latest version from PyPI
response = requests.get('https://pypi.org/pypi/calibrated-explanations/json')
data = response.json()
latest_version = data['info']['version']

# Fetch the sha256 hash from the release files
release_files = data['releases'][latest_version]
sha256_hash = None
for file_info in release_files:
    if file_info['filename'].endswith('.tar.gz'):
        sha256_hash = file_info['digests']['sha256']
        break

if not sha256_hash:
    raise ValueError("Could not find sha256 hash for the latest version on PyPI")

# Read the existing meta.yaml file
with open('recipe/meta.yaml', 'r') as file:
    meta_content = file.read()

# Update the version and sha256 in the Jinja2 template
meta_content = re.sub(r'{% set version = ".*?" %}', f'{{% set version = "{latest_version}" %}}', meta_content)
meta_content = re.sub(r'sha256: .*', f'sha256: {sha256_hash}', meta_content)

# Write the updated meta.yaml file
with open('recipe/meta.yaml', 'w') as file:
    file.write(meta_content)