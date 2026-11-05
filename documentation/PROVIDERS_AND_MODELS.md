# DialogueFoundry providers and models

The base app uses `edge-tts` for Microsoft Edge's online speech service. The
application supplies no user API key for this path, but internet access and the
service's applicable terms still matter. This is an unofficial client, not an
Azure subscription integration or a service availability guarantee. The configured
Edge catalog is limited; it is not a live inventory of every Microsoft voice.

Piper and Kokoro run local CPU inference through optional Python packages and
ONNX Runtime. The application does not require a GPU. Install runtimes as shown in
[Getting started](GETTING_STARTED.md), then use Model library to install assets.
The pinned catalog exposes 28 British/American Kokoro choices and 2,006 Piper
speaker/quality choices across 38 English model variants. Speaker choices sharing
one Piper model do not require separate downloads.

## Model lifecycle

Model library lists known manifests, sizes, license links and installation state.
Download, Verify and Remove are explicit actions. A successful installation uses
verified files and an `installed.json` marker. Copying arbitrary weights into the
folder does not make them trusted or supported. Corrupt or incomplete assets must
be verified/reinstalled. Provider sessions close before model changes; avoid
modifying a model while another application process is using it.

Models live in `%LOCALAPPDATA%\Windows TTS App\models`; previews are in the sibling
`previews` directory. No administrator access is required for this user storage.
The Director CLI accepts `--model-directory` before its subcommand for an explicit
alternative root. The ordinary CLI uses the default root.

The catalog pins Piper upstream revision
`5041a7a49ae5b3a0f30e6837769eb03fdbb231bd`; weights, configs and cards have expected
hashes. Kokoro uses `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the
`model-files-v1.1` release assets, with hashes in
[the manifest](../ttsapp/models/catalog.py). Asset hashes detect unexpected changes;
they do not establish licensing rights or eliminate native-runtime risk.

## Controls and licensing

Local providers support speed 0.5–2.0; source segment settings take precedence
over speaker and job defaults. Explicit Edge speed is unsupported. Accent/locale
and gender are catalog metadata, not emotion, warmth or acoustic quality controls.
Listen to auditions before committing to a cast. Mixed providers are supported
through Director CLI; the desktop planner uses a conversation-wide provider.

Piper cards include public-domain claims, CC attribution/share-alike terms,
noncommercial terms and dataset-specific or incomplete references. Lessac links
to a research dataset agreement. A top-level repository license does not override
these cards. Do not treat every selectable voice as cleared for commercial use or
redistribution. Review the [per-model audit](MODEL_LICENSE_AUDIT.md).

Kokoro's upstream model is Apache-2.0; retain the model card's dataset credits,
including Koniwa and SIWIS. The exported ONNX/style assets also need provenance
review when redistributed. Downloads being separate from the app do not remove
obligations for metadata, copied notices or any assets you redistribute.
See [Licensing](LICENSING.md) before distributing a bundle or generated work.
