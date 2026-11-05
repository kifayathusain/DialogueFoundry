# DialogueFoundry release preparation

This is a build and review procedure, **not distribution clearance**. Version
`1.0.0` is the existing application constant. Do not infer stable readiness or
invent a release/tag/date. Resolve [Licensing](LICENSING.md) and reporting contacts
before announcing a preview. The following procedure requires explicit human
release authorization; preparation does not publish anything.

## Reproducibility

Use Windows x64 and a complete Python 3.10â€“3.13 installation with Tcl/Tk. Record
the source revision, Python/Tcl/Tk versions, architecture, PowerShell version and
package installer version. Current manifests pin Piper 1.8.0 and Kokoro ONNX 0.6.1,
but Edge, ONNX Runtime, PyInstaller and transitive dependencies use ranges or are
unbounded. Benchmark tooling separately pins psutil 7.2.2. The audit's
[installed runtime inventory](third-party/installed-runtime-inventory.json) and
[older build-tool inventory](third-party/build-tool-inventory.json) are evidence,
not a unified release lock. For example, the older package used multidict 7.2.0
while the inspected environment uses 7.2.1.

Before a release, resolve and review a complete Windows CPU dependency set, record
exact wheels/source artifacts with hashes and origin, and retain a tested
constraints/lock plus build-toolchain inputs. Native-library/data provenance must
be checked too. `pip freeze` alone does not capture artifact hashes, external media
or source provenance. Byte-for-byte reproducible packaging has not been established.

## Local build

In a fresh checkout and isolated environment:

```powershell
py -3.13 -m venv .build-venv
.\.build-venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.build-venv\Scripts\python.exe -m pip freeze
.\build-windows.ps1 -PythonExecutable .build-venv/Scripts/python.exe -OutputDirectory dist/preview-review
```

Choose a **new** output directory every time. The script builds a PyInstaller
one-directory full CPU profile, excluding downloaded model weights and optional
GPU frameworks, then generates notices, an inventory and a ZIP. It retains the
executable/archive name `WindowsTTSApp`. This does not rename user storage or the
Python package. Building requires public documentation to be present in the clone.

For an Edge-only build, install `requirements.txt` and the reviewed exact
PyInstaller version (the build requirement range is `>=6.11,<7`) in a separate
environment, then use `-Profile edge`. Review the resulting artifact; an Edge-only
profile does not imply licensing or service-use clearance.

Media tools are external by default. Only after resolving their obligations may
you supply `-FFmpegDirectory` pointing to a directory containing `ffmpeg.exe`,
`ffprobe.exe`, `LICENSE.txt` and `source.txt`. The script records per-binary hashes;
these four files alone do not prove the bundle's legal completeness.

## Artifact and source review

Inspect the ZIP/extracted tree, dependency inventory, full retained licenses,
copyrights and notices. Confirm models and personal files are absent, CPU-only
provider selection is preserved, and public documentation is usable. Run the
notice generator in the exact build environment; retain its incomplete-review
warning until all independently verified obligations are fulfilled.

Include the application `LICENSE` and `COPYRIGHT.md` grant in every package. For
each bundled GPL component, assemble complete matching source, patches,
build/install scripts, toolchain/configuration records and required installation
information. Include a
usable source access mechanism alongside binaries; a table of upstream links is
insufficient. Verify LGPL replacement/recombination requirements, PyInstaller's
exception, MPL covered source, native dependency/data notices, Python/Tcl/Tk and
all optional media-tool obligations. Preserve notices even for dependency code
not directly called when it is still present in the artifact.

## Validation and publication checklist

Run Ruff, relevant automated tests and the full regression suite as described in
[Contributing](../CONTRIBUTING.md), documenting prior findings separately. On a
separate **clean Windows 11 machine/VM**, extract the exact candidate ZIP and test:

1. Launch without development `PATH`, Python or environment assistance.
2. Explicit model download, verification and removal; local preview/playback and
   CPU synthesis after network disconnection.
3. WAV/MP3/M4A output playback, final pauses, replacement protection, normalization,
   Unicode scripts and mixed-provider rendering where advertised.
4. Reconnect for an explicit Edge check; test failure/cancellation/close and storage
   persistence. Run real planning acceptance separately when advertising it.
5. Actual 100%/150%/200% Windows scaling, keyboard access, long documents and lists.

The executable accepts `--diagnostics` with a fresh report directory and optional
`--check-edge` or explicit download flags; inspect `--help` first. Diagnostics run
real checks and do not independently prove clean-machine status. Record OS/package
identity and retain sanitized evidence. Required clean-machine acceptance remains
unmet; development-host results cannot replace it.

Before publication, conduct a **separate secrets and sensitive-history scan** and
review prior exposure, GitHub Issues/private security reporting and conduct
contacts. Configure CI and document signing status; current application signing,
screenshots and demos are follow-up work. Do not fabricate them as release evidence.

Compute SHA-256 of the **final** executable/ZIP/source artifacts, verify extracted
contents against the candidate, and write honest release notes including known
limits, dependency versions, source availability and license/model caveats. Recheck
hashes after any signing or packaging change. A maintainer decides whether and
when to publish; this documentation does not authorize or perform publication.
