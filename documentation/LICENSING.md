# DialogueFoundry licensing

Audit date: **2026-11-06**. Application license: **GPL-3.0-or-later**.
Copyright (C) 2026 Kifayat Husain. The complete, unmodified GNU GPL v3 text is in
[LICENSE](../LICENSE); the application grant, later-version option and scope are in
[COPYRIGHT.md](../COPYRIGHT.md). This grant does not clear all third-party model,
metadata or binary redistribution obligations described below.

## Application license and scope

The full runtime combines Piper 1.8.0 and Phonemizer 3.4.0 (GPL-3.0-or-later),
eSpeak NG GPL components, permissively licensed ONNX/NumPy tooling, and Edge TTS
7.3.1 (mostly LGPLv3 with one MIT file). GPL-3.0-or-later was selected for the
application combination. LGPLv3 permits GPLv3 combination;
the [Apache Software Foundation](https://www.apache.org/licenses/GPL-compatibility.html)
explains Apache-2.0 compatibility with GPLv3. This is not a conclusion that every
binary, dataset, voice or historical contribution is compatible.

The application grant covers application source, original documentation and
original examples owned by Kifayat Husain. Third-party code, adapted templates,
upstream model metadata/cards and voice assets retain their own terms. Preserve
their notices and resolve uncertain provenance or permissions before distributing
them. No ownership of dependencies or upstream material is claimed.

## Audit scope and retained material

[Third-party notices](../THIRD_PARTY_NOTICES.md) and
[the installed inventory](third-party/installed-runtime-inventory.json) record exact
versions, upstream sources, retained texts and their hashes for the runtime
dependency closure on Windows/Python 3.13.17. The
[build-tool inventory](third-party/build-tool-inventory.json) separately records
versions/notices from a prior local QA package. These are evidence snapshots,
not release locks or blanket compatibility certificates. Versions can differ
between the installed environment and that earlier package.

Source review found no explicit copied-code attribution headers in the application
modules; that absence alone cannot prove original authorship. The application
owner has confirmed ownership for the application grant. Third-party provenance
and permissions remain separate review requirements. No third-party screenshots,
icons, recordings or model weights are
tracked in the current application inventory. The English catalog incorporates
upstream model metadata/cards, whose provenance and terms must also be retained
and resolved. Contributor Covenant 2.1 is adapted with its attribution under
CC BY 4.0; its enforcement contact is not configured.

## Source and binary redistribution are different

For a source preview, include the application grant and complete license, preserve
copyright/license notices and resolve permissions for included metadata/assets.
For a binary, inventory what the **actual artifact** contains, including native
DLLs, data, Python/Tcl/Tk, wheel-vendored libraries and the PyInstaller bootloader.
The package notice generator copies available installed license files and public
documentation. It cannot infer absent notices or obtain corresponding source.

For GPL components, comply with the applicable GPL source/object-code provisions.
Provide complete matching Corresponding Source and build/install scripts through
an applicable mechanism, such as equivalent source access alongside binary
downloads under GPLv3 section 6(d). Preserve modifications, configuration, exact
versions, source provenance and any required installation information. A generic
upstream link, dependency table, wheel or source-code repository for only this app
does **not** supply all corresponding source for bundled native components.
Do not promise a written source offer unless prepared to fulfill its exact terms.

LGPL components additionally require the applicable license texts, notices and
rights to modify/recombine or replace the library; assess the actual frozen
packaging method and any GPL option used. Retain MIT/BSD/PSF and Apache copyright,
license and NOTICE material as applicable. MPL-2.0 certifi requires covered-source
availability and preservation of notices when redistributed. NumPy and ONNX Runtime
contain additional bundled-library notices; the top-level package label is
insufficient. PyInstaller's bootloader exception must be retained and verified
for the exact build; it does not remove obligations for other bundled code.

## Open binary evidence gaps

The installed `espeakng-loader` 0.2.4 wheel has **no license assets or license
metadata**. Its DLL reports eSpeak NG **1.52.0**. The upstream build workflow
references the 1.52.0 tag, but exact wheel-to-source/patch/build provenance and
loader-code permission remain unresolved. Piper's `espeakbridge.pyd` reports
**1.52.0.1**, a distinct embedded build requiring its own source provenance.
A retained upstream eSpeak COPYING file supplies the GPL text, not those missing
permissions, data notices or matching source. These are binary publication blockers.

The full PyInstaller hook collects Piper package resources, including ancillary
images/templates and language data even when the app does not call those paths.
Their individual provenance/notices must be reviewed against the extracted
artifact; top-level GPL metadata alone is not clearance for all such assets.

Flatbuffers 25.12.19 omits license files in this installed wheel; a matching
upstream Apache text is retained separately. Audit native component licenses,
embedded data and corresponding source against the final artifact. Python's
license bundle is retained, but a final build also needs the matching Tcl/Tk,
native runtime and platform redistributable notices. Do not assume the Python
package dependency graph inventories every bundled DLL or data file.

## FFmpeg and FFprobe

Media binaries are optional and not tracked. Without explicit bundling, the app
locates user-installed tools on `PATH`. Redistribution obligations attach to any
binaries you choose to ship; invoking a separate executable does not cancel them.
FFmpeg's license depends on configure options and linked libraries. Review the
[official legal guidance](https://ffmpeg.org/legal.html).

The inspected local toolset is Gyan **9.0.2 essentials**, configured with
`--enable-gpl --enable-version3 --enable-static`, including x264/x265 and other
libraries. It is not a generic LGPL-only build. The downloaded archive's recorded
SHA-256 is `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`;
the mutable [Gyan builds page](https://www.gyan.dev/ffmpeg/builds/) is not an
immutable corresponding-source archive. The current builder requires `LICENSE.txt`
and `source.txt`, but a generic download URL in the latter is insufficient evidence
of complete matching source. Obtain the exact source, patches, configuration and
all applicable static-library licenses/source before bundling. Assess any patent
or codec restrictions for intended distribution separately.

## Models, services and outputs

[The model audit](MODEL_LICENSE_AUDIT.md) covers all 38 pinned Piper model cards and
the Kokoro model/style assets. Several Piper references are noncommercial,
research-only or incomplete. These cannot be relabeled GPL or universally cleared.
Separate downloads do not remove obligations for copied metadata or downloaded
assets that you redistribute. Keep model cards, attributions, licenses and source
references with any redistributed model; resolve ambiguous permission first.

Edge TTS library licensing does not grant rights to Microsoft's service. Review
the applicable [Microsoft Services Agreement](https://www.microsoft.com/en-us/servicesagreement)
and service-specific terms; the agreement checked in this audit was published
July 30, 2026 and effective September 30, 2026. Its applicability and permission
for a particular automation/use case must be assessed, not presumed from the
unofficial client. Planning endpoints have their own terms, credentials and costs.

The application's license does not automatically license every script, trained
voice, model dataset, external service or generated output. GPLv3's treatment of
output depends on its content; there is no blanket app-granted output clearance.
Review input rights, model/service terms and any voice/personality rights for the
actual intended use.
