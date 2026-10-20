# Docker image builds

`workflows/docker.yaml` starts the slim image separately from the other variants.
Each call to `workflows/docker-build.yaml` builds amd64 and arm64 on native runners,
then publishes that variant's multi-platform tags as soon as both builds succeed.
Slim publication does not wait for the main, CUDA, or Ollama images. The other
variants run one at a time, with two architecture builds in parallel.

Slim builds export intermediate layers to the GitHub Actions cache, with a separate
scope for each architecture. The first build populates the cache; later builds can
reuse dependency layers. CUDA and other large variants do not export this cache to
avoid evicting slim's layers. Cache export failures do not fail image publication.
Keep frontend build metadata arguments after `npm ci` in the Dockerfile so a new
commit does not invalidate the dependency layer.

`USE_SLIM=true` disables Vite source map generation and keeps Pyodide package wheels
on the CDN. Other builds retain their source maps and bundled wheels. Both image
architectures retain SBOM and provenance generation.

Validate workflow changes with `actionlint` and Prettier. After pushing, compare
slim's queue time, build duration, and manifest publication time in Actions; verify
cache hits on a subsequent build with unchanged dependency manifests.
