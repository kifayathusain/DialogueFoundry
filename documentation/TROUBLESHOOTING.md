# Troubleshooting DialogueFoundry

| Symptom | What to check |
| --- | --- |
| FFmpeg or FFprobe missing | Run both `-version` commands in the shell used to launch the app. Add the media tool `bin` directory to `PATH` and reopen the shell. Both tools are required for validated exports. |
| Packaged media integrity failure | Restore the complete package from a trusted source; do not bypass hash checks. |
| Local runtime missing | Install the selected provider requirements using the exact Python that launches the app. Kokoro requires Python 3.10â€“3.13. |
| Missing/corrupt model | Open Model library, Verify, then reinstall if needed. Runtime packages do not contain the application's downloaded models. |
| Slow first local request | Hash verification, native imports and model loading precede inference. Monitor progress; speed varies by machine. |
| Edge failure | Check connectivity, firewall/proxy policy, voice and service availability. Try fictional input. Local providers require separate setup. |
| Planner failure | Check endpoint, model ID, credentials, consent and offline settings. A local server must already be running and support the expected JSON contract. |
| Permission/output conflict | Choose a writable folder and fresh filename, close software holding the file, or explicitly approve replacement. Check disk space. |
| JSON rejected | Check declared IDs, ranges and duplicate keys. Start with the hello sample. The malformed Lesson is deliberately invalid. |
| No preview sound | Check Windows playback device/volume, audition completion and Stop/Replay state. Playback is Windows-specific. |
| UI clipped at high DPI | Resize, scroll and try keyboard navigation. Actual 150%/200% scaling acceptance remains pending; report scale and resolution. |

Source diagnostics can be invoked explicitly:

```powershell
.\.venv\Scripts\python.exe app.py --diagnostics diagnostics-preview --help
.\.venv\Scripts\python.exe app.py --diagnostics diagnostics-preview
```

Use a new report directory. Diagnostics perform real provider/export checks;
missing models or runtimes may be failures. Downloads require explicit diagnostic
download flags; Edge is checked only with `--check-edge`. Inspect `--help` before
choosing those operations. This is not a mock-only smoke test or evidence of a
clean Windows installation.

Include app version `1.0.0`, source revision, Windows version, Python version,
provider/dependency versions, media-tool versions, sanitized error and minimal
steps when requesting help. Remove private paths, script content, audio, keys and
endpoint credentials before sharing. See [Support](../SUPPORT.md).
