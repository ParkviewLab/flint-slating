# Third-Party Licenses

flint-slating is licensed under the [MIT License](LICENSE). It depends
on third-party libraries that ship under their own licenses, summarized
below. Every direct and transitive runtime dependency at the time of
the current release is **permissive open source** (MIT / BSD / Apache /
ISC / PSF). The CI [`license-check`](.github/workflows/license-check.yml)
workflow runs `pip-licenses` on every pull request and fails the build
if any GPL / AGPL / LGPL / SSPL-licensed package enters the tree.

This file is informational. The authoritative license text for any
dependency lives in that dependency's own distribution (its `LICENSE`
file inside its installed wheel).

## How to regenerate this list

```bash
uv sync --no-dev
uv run pip-licenses --from=mixed --format=markdown --order=license
```

## Runtime dependencies grouped by license

The current runtime dependency tree contains 114 packages on all
platforms (with an additional ~10 platform-conditional packages such as
`pywin32` on Windows and `colorama` on Windows). Counts below are
approximate and drift with version bumps.

### MIT

`PyJWT`, `Faker`, `PyYAML`, `annotated-doc`, `annotated-types`, `anyio`,
`attrs`, `beautifulsoup4`, `cffi`, `charset-normalizer`, `colorlog`,
`docling`, `docling-core`, `docling-ibm-models`, `docling-parse`,
`docling-slim`, `et_xmlfile`, `fastapi`, `filelock`, `filetype`, `h11`,
`httptools`, `httpx-sse`, `jsonref`, `jsonschema`, `jsonschema-specifications`,
`latex2mathml`, `marko`, `markdown-it-py`, `mcp`, `mdurl`, `mpire`,
`openpyxl`, `pdfplumber`, `pdfminer-six`, `pillow` (MIT-CMU / HPND
variant), `pluggy`, `polyfactory`, `pyclipper`, `pydantic`,
`pydantic-core`, `pydantic-settings`, `pylatexenc`, `python-docx`,
`python-pptx`, `referencing`, `rich`, `rpds-py`, `rtree`, `semchunk`,
`setuptools`, `six`, `soupsieve`, `tabulate`, `tree-sitter`,
`tree-sitter-c`, `tree-sitter-javascript`, `tree-sitter-python`,
`tree-sitter-typescript`, `triton` (Linux), `typer`, `typing-inspection`,
`urllib3`, `watchfiles`.

### BSD (2-clause / 3-clause / "BSD License")

`Jinja2`, `MarkupSafe`, `Pygments`, `antlr4-python3-runtime`, `click`,
`colorama` (Windows), `dill`, `fsspec`, `httpcore`, `httpx`, `idna`,
`jsonlines`, `lxml`, `mpmath`, `multiprocess`, `networkx`, `numpy`
(compound BSD-3 + 0BSD + MIT + Zlib + CC0), `omegaconf`, `pandas`,
`psutil`, `pycparser`, `pypdf`, `pypdfium2` (BSD-3 / Apache compound),
`python-dotenv`, `scipy`, `shapely`, `sse-starlette`, `starlette`,
`sympy`, `torch`, `torchvision`, `uvicorn`, `websockets`, `xlsxwriter`.

### Apache-2.0 (any spelling)

`accelerate`, `cuda-pathfinder` (Linux), `hf-xet`, `huggingface_hub`,
`opencv-python`, `python-multipart`, `rapidocr`, `requests`,
`safetensors`, `tokenizers`, `transformers`, `tzdata`.

Compound: `python-dateutil` (Apache + BSD), `uvloop` (Apache + MIT),
`packaging` (Apache OR BSD-2), `cryptography` (Apache OR BSD-3),
`regex` (Apache + CNRI-Python).

### ISC

`shellingham`.

### Python Software Foundation License

`defusedxml`, `typing_extensions`, `pywin32` (Windows).

### Mozilla Public License 2.0 (file-level copyleft)

`certifi`, `tqdm` (compound MPL + MIT).

MPL-2.0 is a **file-level** copyleft license: only modifications to
MPL-licensed source files themselves carry MPL obligations.
flint-slating uses both libraries unmodified, so the MIT distribution
of flint-slating is unaffected.

## NVIDIA proprietary libraries (Linux/amd64 only, conditional)

When torch is installed from the default PyPI index on Linux/amd64, it
pulls in the following NVIDIA CUDA runtime libraries:

`cuda-bindings`, `cuda-pathfinder`, `cuda-toolkit`, `nvidia-cublas`,
`nvidia-cuda-cupti`, `nvidia-cuda-nvrtc`, `nvidia-cuda-runtime`,
`nvidia-cudnn-cu13`, `nvidia-cufft`, `nvidia-cufile`, `nvidia-curand`,
`nvidia-cusolver`, `nvidia-cusparse`, `nvidia-cusparselt-cu13`,
`nvidia-nccl-cu13`, `nvidia-nvjitlink`, `nvidia-nvshmem-cu13`,
`nvidia-nvtx`.

These ship under the **NVIDIA Software License Agreement**, a
proprietary-but-freely-redistributable license. NVIDIA's SLA permits
redistribution of the CUDA runtime libraries verbatim as part of an
integrated application, provided the libraries are not modified and
their license notices are preserved.

The published flint-slating distribution **does not include any of
these NVIDIA libraries**:

- The PyPI distribution and the GHCR container image pin torch to the
  CPU-only PyTorch index (`https://download.pytorch.org/whl/cpu`).
- See [`pyproject.toml`](pyproject.toml)'s `[tool.uv.sources]` and
  `[[tool.uv.index]]` entries.

A user who installs flint-slating into their own environment and then
overrides the torch source to fetch a CUDA-enabled wheel is doing so
under NVIDIA's SLA; that's between them and NVIDIA.

## Bundling notes

The container image at `ghcr.io/parkviewlab/flint-slating` bundles
every runtime wheel listed above. Each wheel contains its own
`LICENSE` / `NOTICE` file inside the installed package directory;
those notices are preserved in the image. Operators redistributing
the container further are bound by the union of those license terms
(all permissive open source, as documented above).
