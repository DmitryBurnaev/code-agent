# Trivy CI scans

`.github/workflows/scan.yaml` runs isolated Linux/amd64 image and filesystem
scans for pull requests to `main`, pushes to `main`, and weekly on Monday at
00:00 UTC. A temporary push trigger for `feature/58-trivy-security-scans` runs
all scan jobs for CI verification; remove that branch from `scan.yaml` before
merging. The image job builds the current checkout's `Dockerfile` `service`
target and records the image ID, architecture, and revision label in the log.
It scans OS and installed language packages with the vulnerability scanner.
The filesystem job scans supported manifests, including `uv.lock` development
dependencies, and infrastructure configuration with `vuln,misconfig`. These
scans do not replace the separate source analysis and secret scanning jobs,
which also run on pushes to `main`, the temporary branch, and the weekly schedule.

Both scans include LOW, MEDIUM, HIGH and CRITICAL findings, including unfixed
vulnerabilities. Any such vulnerability or failed misconfiguration check fails
the job, including LOW findings. UNKNOWN severity is outside this threshold.
The report itself is the input to the failure check, so the two cannot use
different filtering. Valid JSON reports
are uploaded as `trivy-image` and `trivy-fs` for 60 days before the finding
check runs. A download, scan, validation, or upload error fails the job; it is
not a clean scan. Treat artifacts as potentially sensitive and review their
contents before sharing.

Trivy 0.76.2's Linux/amd64 archive is checked against the SHA-256 digest in
the [official release metadata](https://github.com/aquasecurity/trivy/releases/tag/v0.76.2).
That release includes security fixes; the earlier Trivy ecosystem compromise is
documented in [GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23).
The pin prevents later substitution, but does not prove the original release is
safe. Checkout and artifact upload actions are pinned to release commit SHAs.
The GitHub runner, GitHub release hosting, Docker build dependencies and mutable
base image tags and Trivy vulnerability database remain
external trust dependencies and can change independently. Scan results can
therefore change without repository changes. Review these pins and the advisory
history when upgrading.

The filesystem scan uses the checks embedded in the pinned Trivy binary
(`--skip-check-update`), so checks update when Trivy is upgraded. The
vulnerability database still downloads separately, and a failure to obtain it
fails the scan.

## Image-only exception: pip's setuptools SBOM

`trivy-image-ignore.rego` suppresses `CVE-2025-47273`, `CVE-2026-59890`, and
`GHSA-xmj3-9gf7-h52w` only for the `setuptools` 70.3.0 SBOM component with
PURL and BOMRef `pkg:pypi/setuptools@70.3.0` in the inspected linux/amd64
base-image layer. The policy matches both the layer digest and DiffID; any
other CVE, version, package, layer, or installed package remains visible. It
is applied to the image report before the report is uploaded and evaluated;
it is never applied to filesystem scans.

On 2026-11-14 the inspected image
`sha256:2b2346d62e7147ef4b0ca797baf19d5d08ddad01360507acf02033ae71cc19f4`
had no installed or importable setuptools distribution. Its Python 3.13
`ensurepip` wheel contained no setuptools files, although its pip SBOM lists
setuptools 70.3.0. The installed pip 26.3 SBOM also lists that version.
[pip documents](https://github.com/pypa/pip/blob/26.3/src/pip/_vendor/README.rst)
that it retains only `pkg_resources` from setuptools. The affected code is
`PackageIndex` for [CVE-2025-47273](https://github.com/advisories/GHSA-5rjg-fvgr-3xxf),
sdist manifest processing for [CVE-2026-59890](https://nvd.nist.gov/vuln/detail/CVE-2026-59890),
and Windows wheel installation for [GHSA-xmj3-9gf7-h52w](https://github.com/pypa/setuptools/security/advisories/GHSA-xmj3-9gf7-h52w).
These findings describe the SBOM component and were not identified as installed
setuptools code in the inspected image. The ensurepip wheel also carries other
vendored dependencies; this exception does not hide their findings.

Reinspect the actual image, wheel, installed files and advisories when updating
the base image, pip, platform, or scanner, and remove the exception when no
longer needed. A changed layer is deliberately not covered. The separate
setuptools 84.0.0 filesystem finding remains visible and fails the FS job.

For a disposable local check, use a trusted Trivy installation and an isolated
Docker daemon. From the repository root, after reviewing the image build:

```sh
docker build --platform linux/amd64 --target service --tag code-agent:trivy-local .
trivy image --config "" --ignorefile "" --ignore-policy .github/scan/trivy-image-ignore.rego --image-src docker --scanners vuln --severity CRITICAL,HIGH,MEDIUM,LOW --ignore-unfixed=false --format json --output /tmp/trivy-image.json code-agent:trivy-local
trivy fs --config "" --ignorefile "" --skip-check-update --scanners vuln,misconfig --include-dev-deps --severity CRITICAL,HIGH,MEDIUM,LOW --ignore-unfixed=false --format json --output /tmp/trivy-fs.json .
```

Local filesystem scans can include untracked or sensitive files absent from CI;
use a clean disposable checkout and inspect reports before sharing them. A local
scan is not evidence that GitHub Actions ran successfully.
