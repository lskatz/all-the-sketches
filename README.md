# all-the-sketches

Create Mash sketches for all assemblies in the
[all-the-bacteria](https://github.com/AllTheBacteria/AllTheBacteria)
dataset, using GitHub Actions runners.

Assemblies are sourced from the public S3 bucket `allthebacteria-assemblies`,
sketched with [Mash](https://github.com/marbl/Mash), and merged into a single
combined sketch with `mash paste`.

---

## Design constraints

_note_ I used AI to generate a checklist and so this might not be accurate.

| Constraint | Detail |
|---|---|
| Runner disk space | ~10 GB per GitHub-hosted runner |
| Typical assembly size | ~2–5 MB (gzip-compressed FASTA) |
| Assemblies per chunk | ~500–1 000 (download → sketch → delete cycle keeps disk use under 10 GB) |
| Sketch size per genome | ~few KB — sketches are tiny and can be kept in memory / artifact storage |
| All-the-bacteria scale | Millions of genomes — requires many parallel chunk jobs or multiple workflow runs |

The core space-management strategy is **download → sketch → delete**:
download one assembly at a time (or a small batch), sketch it immediately,
then delete the raw FASTA before downloading the next one.

---

## Checklist

### Repository / environment setup

- [ ] Add `mash` to `pixi.toml` dependencies (bioconda channel)
- [ ] Add `python` (or `bash`/`jq`) scripting utilities to `pixi.toml` for
      list-splitting and bookkeeping
- [ ] Verify `awscli` version in `pixi.toml` supports `s3 ls --recursive`
      with `--no-sign-request` for anonymous access to the public bucket
- [ ] Commit a `.github/workflows/` directory skeleton

### AWS / S3 access

- [ ] Confirm the bucket `allthebacteria-assemblies` is publicly readable
      without credentials (`--no-sign-request`)
- [ ] If credentials are needed, add `AWS_ACCESS_KEY_ID` and
      `AWS_SECRET_ACCESS_KEY` as GitHub Actions repository secrets
- [ ] Write a script (`scripts/list_assemblies.sh` or `.py`) that runs
      `aws s3 ls s3://allthebacteria-assemblies/ --recursive --no-sign-request`
      and outputs a plain list of S3 keys (one per line)
- [ ] Cache / commit the full assembly list so workflows can consume it
      without re-listing the bucket on every run

### Chunking strategy

- [ ] Write a script (`scripts/make_chunks.py` or `.sh`) that splits the
      assembly list into fixed-size chunks (e.g. 500 keys per chunk)
- [ ] Store the chunk manifests as numbered files,
      e.g. `chunks/chunk_0000.txt`, `chunks/chunk_0001.txt`, …
- [ ] Decide and document the chunk size that keeps peak disk use safely
      below 10 GB (assembly download + `.msh` file + overhead)
- [ ] Commit the chunk manifests to the repo **or** generate them
      dynamically in a workflow matrix job

### GitHub Actions — chunk-sketch workflow

- [ ] Create `.github/workflows/sketch-chunk.yml`
- [ ] Set the workflow trigger: `workflow_dispatch` with a `chunk_id` input,
      or a matrix strategy that fans out over all chunks
- [ ] Install the pixi environment (`prefix-dev/setup-pixi` action) so
      `mash` and `awscli` are available
- [ ] For each assembly key in the chunk:
  - [ ] `aws s3 cp s3://allthebacteria-assemblies/<key> assembly.fna.gz --no-sign-request`
  - [ ] `mash sketch -o <accession>.msh assembly.fna.gz`
  - [ ] `rm assembly.fna.gz` (free the space immediately)
- [ ] After all assemblies in the chunk are sketched:
  - [ ] `mash paste chunk_<id>.msh *.msh`
  - [ ] Remove the per-assembly `.msh` files to reclaim space
- [ ] Upload `chunk_<id>.msh` — choose one destination:
  - [ ] GitHub Actions artifact (`actions/upload-artifact`) — simple but
        limited to 2 GB per artifact and expires after 90 days
  - [ ] S3 bucket for intermediate sketches (recommended for large runs)
  - [ ] GitHub Release asset (good for a final, stable output)
- [ ] Add a disk-space check step (`df -h`) before and after downloading
      to catch overruns early
- [ ] Add error handling: if a download or sketch fails, log and skip rather
      than aborting the whole chunk

### GitHub Actions — final paste workflow

- [ ] Create `.github/workflows/paste-all.yml`
- [ ] Trigger: `workflow_dispatch`, or automatically after all chunk jobs
      complete (use `workflow_run` or a merge job with `needs:`)
- [ ] Download all `chunk_*.msh` files from the chosen artifact/S3 location
- [ ] Run `mash paste all-the-sketches.msh chunk_*.msh`
- [ ] Upload / publish the final `all-the-sketches.msh`:
  - [ ] As a GitHub Release asset
  - [ ] And/or back to S3 for downstream consumers
- [ ] Record the Mash sketch parameters (k-mer size, sketch size, seed) in
      a provenance file committed to the repo

### Mash sketch parameters

- [ ] Decide on `-k` (k-mer size; default 21 is standard for bacteria)
- [ ] Decide on `-s` (sketch size; default 1000; larger = more accurate but
      bigger files)
- [ ] Decide whether to sketch individual contigs (`-i`) or whole assemblies
- [ ] Document chosen parameters in `README.md` and/or a `params.env` file
      sourced by the workflow

### Testing

- [ ] Create a small test chunk (10–20 assemblies) and run the sketch
      workflow end-to-end manually
- [ ] Verify disk usage stays within the 10 GB budget during the test run
- [ ] Verify `mash paste` produces a valid combined sketch (`mash info`)
- [ ] Add a CI smoke-test job that sketches a handful of assemblies on
      every push to `main`

### Documentation

- [ ] Document how to re-run a failed chunk (rerun just that `chunk_id`)
- [ ] Document how to add newly released all-the-bacteria assemblies
      (append to the list, create new chunk files, run only new chunks,
      then re-paste)
- [ ] Add a `CITATION` or `ACKNOWLEDGEMENTS` section crediting
      AllTheBacteria and Mash

---

## Usage (planned)

```bash
# Install environment
pixi install

# List all assemblies (first-time setup)
pixi run list-assemblies > assembly_list.txt

# Split into chunks
pixi run make-chunks assembly_list.txt

# Sketch a single chunk locally (for testing)
pixi run sketch-chunk chunks/chunk_0000.txt

# Combine all chunk sketches
pixi run paste-all sketches/chunk_*.msh -o all-the-sketches.msh
```

---

## References

- [AllTheBacteria project](https://github.com/AllTheBacteria/AllTheBacteria)
- [Mash documentation](https://mash.readthedocs.io/)
- [GitHub Actions disk space](https://docs.github.com/en/actions/using-github-hosted-runners/about-github-hosted-runners#supported-runners-and-hardware-resources)
- [setup-pixi action](https://github.com/prefix-dev/setup-pixi)
