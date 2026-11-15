package trivy

# Scoped to the inspected linux/amd64 Python base-image layer's SBOM entry.
ignore {
    input.Type == "vulnerability"
    input.PkgName == "setuptools"
    input.InstalledVersion == "70.3.0"
    input.PkgIdentifier.PURL == "pkg:pypi/setuptools@70.3.0"
    input.PkgIdentifier.BOMRef == "pkg:pypi/setuptools@70.3.0"
    input.Layer.Digest == "sha256:f9abc654947e09e316e7703544bd7e68123d383aeb70c5a9cf15be03e71721ce"
    input.Layer.DiffID == "sha256:228d5db3371529ac0f180ac55b7e6d67ca684b63e209bd4efa43915b488bd224"
    input.VulnerabilityID == {"CVE-2025-47273", "CVE-2026-59890", "GHSA-xmj3-9gf7-h52w"}[_]
}
