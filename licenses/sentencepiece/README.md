# SentencePiece notices

The CPython 3.11 Linux wheel for SentencePiece 0.2.1 does not carry standalone
license files. The files in this directory are copied without alteration from
the corresponding upstream release commit
[`31646a467d2051eb904e0b45de3a73e91fe1c1e3`](https://github.com/google/sentencepiece/tree/31646a467d2051eb904e0b45de3a73e91fe1c1e3).
Relative paths below this directory preserve their upstream paths.

- `LICENSE`: Apache License 2.0 for SentencePiece.
- `third_party/absl/LICENSE`: bundled Abseil terms.
- `third_party/darts_clone/LICENSE`: bundled Darts-clone terms.
- `third_party/esaxx/LICENSE`: bundled esaxx terms.
- `third_party/protobuf-lite/LICENSE`: bundled protobuf-lite terms.

The container retains these files under `/opt/fluxyard/licenses/sentencepiece`.
They accompany the pinned wheel and do not license other image components.
