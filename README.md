# hatch go

Hatch plugin for Go builds

[![Build Status](https://github.com/python-project-templates/hatch-go/actions/workflows/build.yaml/badge.svg?branch=main&event=push)](https://github.com/python-project-templates/hatch-go/actions/workflows/build.yaml)
[![codecov](https://codecov.io/gh/python-project-templates/hatch-go/branch/main/graph/badge.svg)](https://codecov.io/gh/python-project-templates/hatch-go)
[![License](https://img.shields.io/github/license/python-project-templates/hatch-go)](https://github.com/python-project-templates/hatch-go)
[![PyPI](https://img.shields.io/pypi/v/hatch-go.svg)](https://pypi.python.org/pypi/hatch-go)

## Overview

A simple, extensible Go build plugin for [hatch](https://hatch.pypa.io/latest/). Build Python extension modules written in Go using cgo.

```toml
[tool.hatch.build.hooks.hatch-go]
verbose = true
path = "."
module = "project"
```

## Dependency license files

License collection is opt-in. `go-licenses` must be installed and available on `PATH`;
the plugin does not install it automatically. The tested collector version is 2.0.1:

```bash
go install github.com/google/go-licenses/v2@v2.0.1
```

```toml
[tool.hatch.build.hooks.hatch-go]
path = "."
module = "project"

[tool.hatch.build.hooks.hatch-go.licenses]
destination = "project/licenses/go"
```

The plugin runs `go-licenses save .` in the configured Go project after a successful
build. Collection uses the build's `GOOS`, `GOARCH`, `CGO_ENABLED`, and Python CGO flags,
plus effective `GOFLAGS` from the environment or Go's persisted configuration.
Dependency-selection flags in `go_build_flags`, including `-tags`, `-mod`, `-modfile`,
`-overlay`, `-compiler`, and instrumentation flags, are passed through `GOFLAGS`.
Explicit build tags override inherited tags. Shell-dependent flags and values that
cannot be represented safely for collection fail rather than being ignored. The
collector uses Go's package loader without external `GOPACKAGESDRIVER` overrides;
the loader disables PGO, so this is not a reproduction of optimization settings.

`destination` is a normalized, wheel-relative **directory**, not a JSON file. Saved
files appear under Go library import paths, for example
`project/licenses/go/example.com/dependency/LICENSE`. Their bytes, filenames, and notices
remain unchanged. The directory is generated outside the project and force-included in
standard and editable wheels, then removed after packaging. Source distributions do not
run collection or contain these temporary files. Existing destinations, conflicting forced
inclusions, and paths rewritten by Hatch sources are rejected. Each saved file is included
explicitly so Hatch's directory filters do not remove collector artifacts.

For editable installations, use `importlib.metadata.distribution(...).locate_file(...)`
to locate installed license resources. Source-package resource APIs may not see
force-included files stored in the editable wheel.

Missing or unknown licenses, collector failures, empty license texts, and saved symlinks
fail the build. This applies to the root Go package as well as dependencies: the collector
needs an original license file for the project. Unknown options are rejected; there is no
blanket ignore or generic license-text substitution. `SKIP_HATCH_GO`, `skip = true`, and
source-distribution builds also skip collection. Builds without `licenses` are unchanged.

### Scope and review

The inventory covers direct and transitive Go packages selected by the build environment;
it is not a complete module graph or a trace of linked symbols. Test-only and inactive
target/tag dependencies are excluded. `go-licenses` groups packages by their selected
license file, and its directory output is not a versioned SBOM.

The collector saves licenses and adjacent `NOTICE`, `NOTICE.txt`, or `NOTICE.md` files.
For some license classifications it copies the **entire source directory containing the
license**, excluding only Git metadata. This can increase wheel size and include unrelated
local files. Review that output before shipping, especially with local replacements or
workspace dependencies; the plugin does not remove potentially required source files.

Go's standard library/runtime is excluded by the collector. It also cannot discover
dependencies hidden in C/C++, assembly, system libraries, or separately vendored assets.
Collector warnings remain visible. Review runtime licenses and native dependencies
separately; collecting files does not certify license compatibility or compliance.

> [!NOTE]
> This library was generated using [copier](https://copier.readthedocs.io/en/stable/) from the [Base Python Project Template repository](https://github.com/python-project-templates/base).
