set -e
BASE="https://storage.googleapis.com/flyem-male-cns/v1.0/connectome-data/flat-connectome"
cd data/malecns
for f in body-annotations-male-cns-v1.0-minconf-0.5.feather \
         body-neurotransmitters-male-cns-v1.0.feather \
         connectome-weights-male-cns-v1.0-minconf-0.5.feather; do
  if [ -f "$f" ]; then echo "have $f"; continue; fi
  echo "fetching $f"
  curl -sS --fail --retry 3 -o "$f.part" "$BASE/$f" && mv "$f.part" "$f"
  echo "done $f ($(du -h "$f" | cut -f1))"
done
echo "ALL DONE"
