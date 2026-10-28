# Reconstruction status

Work in progress. This implementation targets jq 1.8.2 as described by the
Recipkg jq recipe; it is not yet compatible. Its parser, builtins, assignments,
control flow, JSON parsing, input/output options, streaming, modules, library
API, numeric precision, platform behavior and performance need substantial
work. The upstream jq executable is not used as a runtime dependency.

The `recipkg/standard-library-verification` jq samples are the initial
independent black-box acceptance suite. Failed and skipped tests must remain
visible; passing a subset does not establish full reconstruction.

## Local baseline: 2026-10-29

- Input: `recipkg/jq` v0.1.6, commit `922540c1c1f7a1c3dc9a24ea4df351a6757af8d4`, including its recursive `software-quality` dependency. The full archive was packed and checked and the build prompt generated; upstream source was not used as implementation input.
- Environment: Linux, Python 3.14.8; candidate executable `./jq`, with no dependency on an installed jq. The verification repository was at commit `fc2189d9fb565bdb177adfe6c3528274c26a518f`.
- Command from the verification checkout: `RECIPKG_TEST_JQ=/absolute/path/to/jq-source/jq python3 -m unittest discover -s tests -p test_recipes.py -k JqSamples -v`.
- Result: 12 test methods ran, 4 passed without failing subtests; 8 methods had failures, totaling 48 failed assertions/subtests. Assignment samples, optional/catch samples, basic filter/raw/slurp/variables, and basic exit-status/invalid-JSON samples passed. These are finite examples, not a claim that their feature families are complete.
- Unresolved examples include functions and variable binding, reductions, conditions and comparison edges, decnum, file inputs, JSON encoding/error behavior, sequence mode, NUL output and streaming. No public C library API, platform validation, performance measurement or full upstream test suite has been completed. The recipe itself still lacks requirements necessary for full reconstruction.

## Input-stream iteration: 2026-10-29

- Input: recipe v0.1.8 at `0f25aaae9c2f6ddf71c3c256ed85185dff5070c0`, with recursive quality dependency; verification at `d3ef5883bd32fc8561354a7d0bedd7b24f99a065`. The recipe corrects `-n` and describes observed cross-file boundaries before this implementation was updated.
- The same jq sample command above ran 13 methods: 7 passed without failing subtests; 6 had failures, totaling 45 failed assertions/subtests. The input/inputs, file, slurp and NUL-output samples passed; all 13 methods passed on the local upstream `jq-1.8.2` reference. Additional direct comparisons covered raw CRLF, empty input, consuming input twice and EOF.
- The input reader currently buffers each file or stdin in memory; it is not a bounded-memory streaming implementation. JSON grammar, malformed data across boundaries, invalid UTF-8, files and stdin in more combinations, and platform-specific behavior remain incomplete. Language, decnum, streaming record output, sequence mode, full API and performance remain unverified or failing. These sample results do not establish full compatibility.
