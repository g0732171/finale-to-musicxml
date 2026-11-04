# Finale to MusicXML

An offline application for converting Finale **MUSX and some legacy MUS scores**
to compressed MusicXML (`.mxl`). The application window is called **Finale Archive**.
It runs on your own computer and opens a Japanese web interface in your browser.

[日本語の操作説明](README-ja.txt) · [中文说明](README.zh-CN.md) ·
[Download Windows / Mac builds](https://github.com/g0732171/finale-to-musicxml/releases/latest)

This is **score-file conversion**, not audio conversion or PDF-to-score recognition.
It is an independent community project, not an official Finale/MakeMusic product.

## Use the offline application

1. Download the Windows or Mac ZIP from [Releases](https://github.com/g0732171/finale-to-musicxml/releases).
2. Extract the **entire** ZIP.
3. Windows: double-click `Start-Windows.cmd`. Mac: double-click `Start-Mac.command`.
4. Select **one file** or **a folder**, then press the conversion button.

The portable ZIPs include Python and their dependencies. End users do not need
Python, Finale, a server, an account, or an Internet connection to convert scores.
Mac downloads support Apple Silicon and Intel. If separate CPU-specific ZIPs are
offered, choose the one matching your Mac. Universal builds contain both runtimes.
**Mac startup and native
pickers have not yet been verified on an actual Mac.**

Results go into a new sibling folder named `<source>_変換済み`. Existing results
are preserved by adding a number. Subfolders and filenames are retained. Originals
are never edited, and conversion folders contain only MXL files, without CSV/log
reports. Preview, individual downloads, and a ZIP download are also available.

## What this project adds

This application stands on the substantial work of the upstream projects below.
It does **not** claim to have independently invented their parsers or algorithms.

- A portable local application with native Windows/Mac file and folder selection.
- Batch conversion, progress, sibling output folders, and safe filename collisions.
- A Japanese interface with bundled offline score preview.
- Additional MUS record-layout handling, four-layer traversal, deleted-record
  filtering, and correct treatment of positioned rests.
- MUSX tempo compatibility handling, including duplicate markings and music-font
  glyphs that otherwise appear as text such as `% =65`.
- Bounded conversion workers, loopback-only access checks, and regression tests.

## Compatibility and limits

- MUSX uses `musx2mxl`; MUS uses record decoders and the MusicXML exporter from
  `finale-file-parser`, with application compatibility handling in `app/mus_compat.py`.
- Only **some** old MUS structures are supported. Unverified or ambiguous critical
  record layouts are rejected. ETF is not supported.
- Successful parsing is not a guarantee of an exact copy of the original score.
  Part names, piano grand-staff grouping, percussion, transpositions, expressions,
  and page layout may require checking and correction in a notation editor.
- File limits: 20 MB per input, 5,000 files per batch, 90 seconds per conversion.
- Windows 10/11 x64 and macOS 11+ are the intended portable-build targets.
- Tests that vary a version banner only check that the reader does not reject that
  banner; they do **not** establish complete support for a real Finale release.

## Privacy and local operation

The application binds only to `127.0.0.1` on an available port and uses a random
session token. Native selection, conversion, saving, and preview run locally.
Conversion workers block outbound network connections. Closing the browser does
not immediately stop a running batch; use the page's **終了** button to quit.
An idle service exits after 30 minutes.

No customer scores, private test corpus, server deployment, tunnels, credentials,
or hosted service are included in this repository. Build/setup commands below
download dependencies; running a portable build does not.

## Run from source

Clone the source repository for these developer commands. Use Python **3.12 or
newer** with Tk available on Windows.

```sh
python -m venv .venv
# Activate .venv for your shell, then:
python -m pip install --no-deps -r requirements.txt
python tools/fetch_assets.py
python -I app/server.py
```

Windows activation: `.venv\Scripts\activate`. Mac activation: `source .venv/bin/activate`.

`--no-deps` is intentional. The upstream MUSX package's metadata targets its
original Tk drag/drop GUI and an older lxml version, and the MUS parser declares a
report renderer. This application uses their conversion modules with the explicit,
tested versions in `requirements.txt`; the original GUIs/report renderer are not used.

`fetch_assets.py` obtains the pinned OpenSheetMusicDisplay bundle and checks its
SHA-256. This setup step needs Internet access. The bundle is included in portable
release ZIPs so preview works offline.

## Test

```sh
python -m unittest discover -s tests -v
```

Public tests generate their own tiny MUS fixtures, exercise record layouts, byte
orders, all four layers, deleted slots, positioned rests, malformed references,
alternate compression levels, loopback APIs, and output preservation. A small MUSX
fixture comes from the MIT-licensed `openmusx/musxdom` project; its exact provenance
and hash are in [the fixture notes](https://github.com/g0732171/finale-to-musicxml/blob/main/tests/fixtures/README.md).

No test opens a native picker or a browser window. CI runs the public suite on
Windows, macOS, and Linux. This does not constitute native Mac UI validation.
Additional private pre-release checks used nine customer MUS files and four
publisher-provided MusicXML comparisons; those materials are **not redistributed**
and are not part of public CI.

## Build portable ZIPs

```sh
python tools/bundle.py prepare
python tools/bundle.py package
# Optional smaller Mac downloads, one per CPU:
python tools/make_mac_variants.py
```

The builder downloads pinned standalone CPython runtimes and wheels, validates
their recorded hashes, preserves notices, and packages Windows plus a dual-runtime
Mac ZIP under `release/`. These generated artifacts and caches are ignored by Git.
The Mac archive is assembled with executable permissions and symlinks preserved;
building it on Windows is not a substitute for testing it on a Mac.

## Credits and license

The application-specific code is MIT licensed; dependencies and borrowed/adapted
portions retain their original notices. See [LICENSE](LICENSE), [THIRD-PARTY.txt](THIRD-PARTY.txt),
and [LICENSES/](LICENSES/).

| Project | Contribution | License |
| --- | --- | --- |
| [musx2mxl](https://github.com/joris-vaneyghen/musx2mxl) — joris-vaneyghen | MUSX conversion engine | MIT |
| [finale-file-parser](https://github.com/jsawruk/finale-file-parser) — jsawruk | MUS record decoding and MusicXML export | MIT, with separately attributed components |
| [OpenSheetMusicDisplay](https://github.com/opensheetmusicdisplay/opensheetmusicdisplay) — PhonicScore | Browser score preview | BSD-3-Clause |
| [musxdom](https://github.com/openmusx/musxdom) — Robert G. Patterson | Public MUSX test fixture and upstream format research | MIT |
| [Python](https://www.python.org/) / [python-build-standalone](https://github.com/astral-sh/python-build-standalone) | Portable runtime | PSF and bundled component notices |
| [lxml](https://lxml.de/) / [defusedxml](https://github.com/tiran/defusedxml) | XML processing | See their distribution notices |

Contributions with small, legally shareable test cases and independent MusicXML
comparisons are welcome. Please do not attach client or unpublished scores to public
issues without permission; an unsupported format is preferable to silently lost music.
