#!/bin/sh
# Sign, notarize and staple release/Jotva-app.dmg (electron-builder only notarizes the
# .app inside it). Uses the Developer ID certificate in the login keychain and the
# "jotva-notary" notarytool profile (xcrun notarytool store-credentials).
set -eu
DMG="release/Jotva-app.dmg"
IDENTITY="${JOTVA_SIGN_IDENTITY:-Developer ID Application}"
PROFILE="${APPLE_KEYCHAIN_PROFILE:-jotva-notary}"
codesign --force --sign "$IDENTITY" --timestamp "$DMG"
# notarytool exits 0 even when Apple rejects the file, so check the verdict.
RESULT=$(xcrun notarytool submit "$DMG" --keychain-profile "$PROFILE" --wait)
echo "$RESULT"
echo "$RESULT" | grep -q "status: Accepted" || { echo "Apple did not accept $DMG" >&2; exit 1; }
xcrun stapler staple "$DMG"
spctl -a -t open --context context:primary-signature -v "$DMG"
