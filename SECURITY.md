# DialogueFoundry security policy

There is no designated supported stable release or security maintenance branch.
The current source reports `1.0.0` and remains a preview. No response-time or
backport commitment is made. Evaluate updates and all optional native runtimes
before using the application with sensitive material.

## Private vulnerability reporting

**A private reporting channel has not yet been configured.** GitHub's repository
API reported private vulnerability reporting **disabled on 2026-11-06**. Do not post
vulnerability details, exploit files, secrets or private scripts in public issues,
discussions or pull requests.

Before public preview publication, the maintainer must enable and test a private
GitHub reporting route or publish a monitored private security contact here.
Until that route is published, withhold sensitive details. An ordinary public
issue may request that a private channel be established, but must contain no
vulnerability specifics. See [Support](SUPPORT.md) only for nonsensitive problems.

A private report should include affected source/package version, provider/runtime
versions, impact, minimal sanitized reproduction and suggested mitigation. Share
private data only when needed through the established private route.

Model checksums and bounded JSON parsing are useful controls, not proof of safety.
Native runtimes, media binaries and model files require trusted provenance and
dependency review. A separate secrets/sensitive-history scan is a publication
prerequisite; this documentation task does not certify repository security.
