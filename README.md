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

> [!NOTE]
> This library was generated using [copier](https://copier.readthedocs.io/en/stable/) from the [Base Python Project Template repository](https://github.com/python-project-templates/base).
