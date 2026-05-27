#!/bin/bash
set -euo pipefail

thisDir=$(dirname "$0")
dataDir="$thisDir/../data"
mkdir -pv $dataDir

# Find out what the latest filename is called
aws s3 ls --no-sign-request \
  s3://allthebacteria-metadata/allthebacteria-assemblies/assemblies-list/data/  | \
  sort | tail -n1 \
  > $dataDir/latest_assemblies.txt

latestAssemblies=$(cat $dataDir/latest_assemblies.txt | perl -lane 'print $F[3];')

aws s3 cp --no-sign-request \
  s3://allthebacteria-metadata/allthebacteria-assemblies/assemblies-list/data/$latestAssemblies \
  $dataDir/latest.tsv.gz

