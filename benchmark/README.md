# Benchmark

Suites are pinned in [`configs/benchmark.toml`](../configs/benchmark.toml); sources are
listed with their verified commits in `docs/literature/verified-sources.md`.

```bash
restgen benchmark fetch      # partial clones at the pinned commits -> projects/suites/<suite>
restgen benchmark verify     # HEAD == pinned commit and no tracked file modified
restgen benchmark setup -s booking   # service venv -> projects/services/<service>/.venv
```

| Suite | Kind | Runnable here now |
|---|---|---|
| restgym | 11 JVM services (Docker, JaCoCo, mitmproxy) | not yet: container launch is not implemented |
| wfd | JVM REST/GraphQL/RPC SUTs (docker-compose) | not yet: container launch |
| wafp | Python/JS/Go/Rust targets (docker-compose) | not yet: container launch; 2023 deps unchecked |
| restestbench | 3 services + NL requirements + mutants | not yet: container launch + mutation runner |
| prab | OpenAPI documents only | specs only by design (never server coverage) |
| schemathesis-examples | `booking` FastAPI toy API | yes (development, artificial) |

Docker is not installed on the development machine; rootless Podman 5.8 is, and is
the intended container runtime. A service is only added to the manifest together with
its launch, health check and coverage settings.
