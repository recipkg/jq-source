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

## Condition and comparison iteration: 2026-10-29

- Input: recipe v0.1.9 at `2861523993aba230b206214c1c14470c7eeb026c` with its recursive quality contract; verification at `0c3f600159450fa95ce28e3a77f3b30f3378039e`. The recipe and verification include nested boolean/number comparison examples.
- The jq sample suite ran 13 methods: 8 passed without failing subtests; 5 had failures, totaling 30 failed assertions/subtests. All 13 methods passed on the local upstream `jq-1.8.2` reference. The newly passing method covers the documented condition, short-circuit and comparison examples.
- A separate deterministic differential test compared 138 cases of nested JSON equality, sorting and conditionals with that reference. Run it with `RECIPKG_TEST_JQ=/absolute/path/to/jq-source/jq RECIPKG_TEST_JQ_REFERENCE=/usr/bin/jq python3 -m unittest discover -s tests -p test_jq_differential.py -v` from the verification checkout. It is finite and does not establish complete compatibility.
- Numeric precision, non-finite numbers, all expression precedence and object syntax, functions and bindings, reductions, JSON edge cases, sequence mode, streaming, library APIs, performance and other platforms still require implementation or verification. The implementation buffers individual files and stdin in memory.

## Binding and reduction iteration: 2026-10-29

- Input: recipe v0.1.10 at `004686a531037259782d955b2c8bdc9e8579c1a2`, with its recursive quality contract; verification at `e3deba0367bdf471fc88f2d9136bdcc708c81266`. The packed archive was checked and its complete build prompt rendered.
- Added lexical variable bindings, basic array and object destructuring, numeric subtraction and multiplication, and selected `reduce` and `foreach` behaviors. Undeclared variables are checked before reading input. Multiple-result and empty-result examples are covered, including observed differences between `reduce` and `foreach` with multiple initial values; behavior outside the recorded examples remains uncertain.
- The local jq sample suite ran 14 methods: 9 passed without failed subtests; 5 methods failed, totaling 15 failed assertions/subtests. All 14 methods passed against the local jq 1.8.2 reference. A separate deterministic differential suite compared 100 binding/reduction cases and 138 comparison/sorting/conditional cases against that reference; all passed. These finite tests do not establish compatibility for entire feature families.
- User-defined functions, full binding patterns and multi-value semantics, number precision, JSON parsing boundaries, sequence mode, streaming, library APIs, performance and other platforms still require implementation or verification. The reader buffers individual files and stdin in memory.

## Function iteration: 2026-10-29

- Input: recipe v0.1.11 at `66445effd45a3656bf3cecd59be8dc0e7df57b38`, with its recursive quality contract; verification at `3a28ea39793734d29b095ee56bba639cf11fad2f`. The archive was packed, checked and rendered into a complete build prompt.
- Added selected user-defined functions, lexical closures, recursion, filter and value parameters, multiple arguments and compile-time checks for reachable definitions. Cases cover shadowing, unused definitions, multiple outputs, empty arguments and mid-stream errors. This is not a complete jq compiler; other functions, builtins, modules, scoping cases and recursion limits remain unverified.
- The local jq sample suite ran 15 methods: 11 passed without failed subtests; 4 methods failed, totaling 8 failed assertions/subtests. All 15 methods passed against the local jq 1.8.2 reference. A separate deterministic differential suite compared 100 function cases, 100 binding/reduction cases and 138 comparison/sorting/conditional cases with that reference; all passed. These finite examples are not full compatibility.
- Number precision, JSON parsing boundaries, sequence mode, streaming, full language behavior and builtins, library APIs, performance and other platforms still require implementation or verification. The reader buffers individual files and stdin in memory.
