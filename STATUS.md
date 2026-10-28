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
