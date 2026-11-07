"""Write installed Python and locked npm metadata; this is not legal clearance."""
from importlib import metadata
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
lock = json.loads((root / 'apps/mobile/package-lock.json').read_text())
items = []
for path, package in lock['packages'].items():
    if not path:
        continue
    name = package.get('name') or path.rsplit('node_modules/', 1)[-1]
    items.append({'ecosystem': 'npm', 'name': name, 'version': package['version'],
                  'license': package.get('license', 'REVIEW_REQUIRED'),
                  'source': f'https://www.npmjs.com/package/{name}/v/{package["version"]}',
                  'license_location': 'docs/licenses/expo-sdk54-MIT.txt (upstream SDK 54)' if name == 'expo-media-library' else f'apps/mobile/{path}/LICENSE*'})
for distribution in metadata.distributions():
    name = distribution.metadata['Name']
    license_name = distribution.metadata.get('License-Expression')
    if not license_name:
        license_name = '; '.join(c.removeprefix('License :: ') for c in
                                 distribution.metadata.get_all('Classifier', []) if c.startswith('License :: '))
    items.append({'ecosystem': 'pypi', 'name': name, 'version': distribution.version,
                  'license': license_name or 'REVIEW_REQUIRED',
                  'source': f'https://pypi.org/project/{name}/{distribution.version}/',
                  'license_location': 'Installed distribution .dist-info/licenses or LICENSE metadata'})
result = {'scope': 'Locked mobile packages and current Python environment; excludes OS/container packages.',
          'clearance': 'Metadata inventory only. Commercial hosting/distribution, attribution, copyleft and unknown licenses require owner/legal review.',
          'dependencies': sorted(items, key=lambda p: (p['ecosystem'], p['name'], p['version']))}
(root / 'docs/dependency-inventory.json').write_text(json.dumps(result, indent=2) + '\n')
print(f'Inventoried {len(items)} dependency records')
