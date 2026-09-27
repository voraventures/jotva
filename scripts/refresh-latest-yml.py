"""After the DMG is signed, notarized and stapled, its bytes differ from what
electron-builder hashed into release/latest-mac.yml. Refresh that entry."""
import base64, hashlib, pathlib, re

yml = pathlib.Path("release/latest-mac.yml")
dmg = pathlib.Path("release/Jotva-app.dmg")
data = dmg.read_bytes()
sha = base64.b64encode(hashlib.sha512(data).digest()).decode()
text = yml.read_text()
text = re.sub(r"(- url: Jotva-app\.dmg\n\s+sha512: )\S+(\n\s+size: )\d+", rf"\g<1>{sha}\g<2>{len(data)}", text)
yml.write_text(text)
print("latest-mac.yml: Jotva-app.dmg entry refreshed")
