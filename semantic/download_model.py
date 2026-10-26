"""Build-time download of fixed public weights; never runs Hub Python code."""
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

manifest=json.loads(Path('model.json').read_text())
folder=Path('model')
folder.mkdir(exist_ok=True)
for filename,expected in manifest['files'].items():
    destination=folder/Path(filename).name
    url=f'https://huggingface.co/{manifest["repository"]}/resolve/{manifest["revision"]}/{filename}?download=true'
    digest=hashlib.sha256()
    total=0
    print('Downloading fixed artifact: '+filename,flush=True)
    with urlopen(url,timeout=120) as response, destination.with_suffix('.part').open('wb') as out:
        while chunk:=response.read(1024*1024):
            total+=len(chunk)
            if total>200*1024*1024:
                raise RuntimeError('Model artifact exceeds size limit')
            digest.update(chunk)
            out.write(chunk)
    if digest.hexdigest()!=expected:
        raise RuntimeError('Model artifact checksum mismatch: '+filename)
    destination.with_suffix('.part').replace(destination)
    print('Verified SHA256: '+filename,flush=True)
