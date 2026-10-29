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

## Streaming iteration: 2026-10-29

- Input: recipe v0.1.12 at `facc71ce64053ed2001d773ce315dda2345d1853`, with recursive quality contract; verification at `bc48da71991cc8c91844a965d4197813bba2a5c0`. The archive was packed, checked and rendered as a complete build prompt.
- Implemented selected `--stream` and `--stream-errors` path records, empty and nonempty containers, partial-input errors, slurp/input integration, and chunked input including the recorded cross-file case. The local jq sample suite ran 16 methods: 13 passed without failed subtests; 3 methods failed, totaling 6 failed assertions/subtests. All 16 methods passed against local jq 1.8.2.
- The deterministic differential suite passed 100 function, 100 binding/reduction, 138 comparison/sorting/conditional, 102 valid stream and 20 malformed stream cases against that reference. These are finite samples, not a complete grammar, performance test or compatibility guarantee.
- Inputs are read in chunks, but ordinary JSON values and individual stream strings can still accumulate in memory; no bounded-memory or throughput target has been measured. Stream numeric extensions, all malformed/Unicode cases, error wording, sequence mode interactions and real-time output buffering need further work. Number precision, broader JSON boundaries, language and builtins, library APIs and other platforms remain incomplete.

## JSON sequence iteration: 2026-10-29

- Input: recipe v0.1.13 at `1b492446698b06cf3be175cbc0d5917934498281`, with recursive quality contract; verification at `488428eb206b409629b75af9324e8c9e696f76eb`. The packed archive was checked and rendered as a complete build prompt.
- Added selected `--seq` record framing, error resynchronization, stream/stream-errors, slurp, explicit input, raw output and truncated top-level numeric handling. The local jq suite ran 17 methods: 15 passed without failed subtests; 2 failed, totaling 5 failed assertions/subtests. All 17 methods passed against local jq 1.8.2.
- A deterministic differential suite compared 72 sequence cases plus 460 previously recorded function, binding, ordering and stream cases with the reference. All passed. These examples do not establish full compatibility, error wording equivalence or performance.
- Each sequence segment is currently buffered before processing. Number precision, JSON parsing boundaries, broader sequence semantics, stream grammar, library APIs, full language behavior and builtins, performance and other platforms remain incomplete or unverified.

## JSON decoding iteration: 2026-10-29

- Input: recipe v0.1.14 at `467a5963c89937cb742de52aa8cb3512f8dfba93`, with recursive quality contract; verification at `6dfb34564f3d8ced8c69cd053eeeb3bbf35091b7`. The archive was packed, checked and rendered with complete recursive context.
- Added selected relaxed numeric literals, nested arrays and objects, low-surrogate replacement and high-surrogate rejection in normal and streaming input. Previously emitted values remain visible on later parsing failures. These are partial parsing semantics, not the complete jq JSON grammar.
- The jq sample suite ran 18 methods: 17 passed and the decnum method failed at its capability check; the newly added decnum byte-format examples were not reached. All 18 methods passed against local jq 1.8.2. The deterministic differential suite passed 104 relaxed-literal and Unicode cases plus 532 previously recorded function, binding, ordering, stream and sequence cases against that reference. Results are finite samples, not complete compatibility.
- The implementation still uses Python numeric types rather than jq's decnum representation: literal precision, negative zero, exponent formatting, extreme magnitudes and arithmetic conversion are incomplete. Ordinary values and sequence segments may accumulate in memory; performance, complete stream grammar, other platforms, library APIs and substantial language and builtin coverage remain unverified.

## Decimal samples iteration: 2026-10-29

- Input: recipe v0.1.15 at `038c7544f33fcdba619bb879aa9083950a4ebddd`, with the recursive quality contract; verification at `73ffcdc4ec0e1f744853cc7fcb8fee50f7bb3699`. The archive was packed, checked and rendered with complete recursive context.
- Decimal literals now retain selected precision and exponent forms, including negative zero; arithmetic uses double precision, with output formatting adapted to observed jq samples. `have_decnum` reports the supported decimal-preservation capability here; this Python implementation does not use jq's decnum library and does not establish equivalent behavior in all cases.
- All 19 finite jq black-box sample methods passed. The expanded eight-method differential suite compared 300 additional literal, comparison and arithmetic cases with jq 1.8.2: four arithmetic subtests failed on decimal-to-double rounding; the other seven methods passed. Examples include input `5253265562710.54996e4` and `351060153116105761.9598`. The failures remain in the verification suite. An independent earlier 200-case numeric sample passed, but that does not supersede these failures.
- The decimal conversion and float output algorithms have not been established across the full range; numeric indexes and other types have only selected coverage. Ordinary values and sequence segments may accumulate in memory; performance, complete stream grammar, other platforms, library APIs and substantial language and builtin coverage remain unverified.

## Decimal rounding iteration: 2026-10-29

- Input: recipe v0.1.16 at `b63791230c951cb6cd1d1e7b918a6c964072e3db`, with its recursive quality contract; verification at `cf2ab6f79269e15949f90cffdbf2bb5d623ce034`. The archive was packed, checked and rendered with complete recursive context.
- For ordinary finite values the implementation now rounds to 17 decimal significant digits with ties to even before converting to double, following observed jq 1.8.2 decnum behavior. The four previously failing arithmetic cases pass. Conversion outside the finite double range still uses direct conversion to preserve overflow and underflow handling.
- The 19-method jq sample suite and nine-method differential suite passed against local jq 1.8.2. The latter includes 2,509 exact-byte decimal boundary cases and 300 exact-byte literal, comparison and arithmetic cases, as well as the existing finite stream, sequence, parser, scope, ordering and reduction samples. These results are not proof of full numerical or language compatibility.
- This implementation does not use jq's decnum library. Extreme precision/exponents, formatting, full parsing and language behavior, library APIs, memory bounds, performance and other platforms remain unverified.

## Collection and key filters iteration: 2026-10-29

- Input: recipe v0.1.17 at `deaa91370f50d1416cfbf5399816f740fbd2e382`, including its recursive quality contract. The archive was packed, checked, and rendered before implementation. Verification was at `39a90e9bf52336da362366b1b126ba05fd8e5aab`.
- Implemented selected `map`, `map_values`, `keys`, `keys_unsorted`, `has`, and `in` behavior. In particular mapping preserves all filter results, whereas `map_values` takes only the first and drops keys or elements when there is no result; membership errors preserve earlier independent outputs. The implementation still does not claim all behavior of these filters or the jq standard library.
- The new explicit examples and a differential sample of 1,400 fixed-seed input/filter combinations passed against local `jq-1.8.2`; the previous implementation had 37 failing assertions or subtests on these cases. The reference-only run skips the differential method by design. The existing 19-method jq sample suite and nine-method differential suite also passed for the reconstruction. The local reference's exact binary build provenance remains unverified.
- Other jq builtins and language features, extreme indices and numeric behavior, library APIs, platform coverage and performance remain incomplete or unverified. These finite checks do not establish full compatibility.
