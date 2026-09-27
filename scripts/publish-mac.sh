#!/bin/sh
# Publish the notarized Mac build as GitHub release v<version> (see npm run release:mac).
# Uploads what people and the in-app updater need:
#   Jotva-app.dmg            first-time download (website's Download button)
#   Jotva-<v>-arm64-mac.zip  what installed copies update from (+ .blockmap)
#   latest-mac.yml           the version file the updater checks
# Usage: sh scripts/publish-mac.sh path/to/release-notes.md
set -eu
NOTES="${1:?release notes file}"
VERSION=$(node -p "require('./package.json').version")
TAG="v$VERSION"
ZIP="release/Jotva-$VERSION-arm64-mac.zip"
for f in release/Jotva-app.dmg "$ZIP" "$ZIP.blockmap" release/latest-mac.yml; do
  [ -f "$f" ] || { echo "missing $f — run npm run release:mac first" >&2; exit 1; }
done
if gh release view "$TAG" --repo voraventures/jotva >/dev/null 2>&1; then
  gh release upload "$TAG" release/Jotva-app.dmg "$ZIP" "$ZIP.blockmap" release/latest-mac.yml --clobber --repo voraventures/jotva
else
  gh release create "$TAG" release/Jotva-app.dmg "$ZIP" "$ZIP.blockmap" release/latest-mac.yml \
    --repo voraventures/jotva --target main --title "Jotva $VERSION" --notes-file "$NOTES"
fi
