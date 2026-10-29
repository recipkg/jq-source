# jq reconstruction — work in progress

This is an independent implementation based on the Recipkg jq recipe. It is not
the upstream jq source, a wrapper around an installed jq, or a complete jq
replacement. Its current supported grammar and CLI options are intentionally
limited; unsupported syntax must fail rather than silently produce results.
Use Python 3.11 or newer and run `./jq --version` or `./jq -c '.items[] | .name'`.

The target remains the full behavior of jq 1.8.2, including its libraries,
streaming, errors, precision and platforms. The current recipe is incomplete,
so missing specifications and failed or unrun compatibility tests are tracked
as unresolved work. See `STATUS.md` before using this implementation.

The current module slice supports explicit `-L` directories and recursive
`include` of `.jq` files in the observed flat and nested layouts. Imports,
module metadata, JSON modules and jq's default module paths are explicitly
unsupported; the finite acceptance results and remaining boundaries are in
`STATUS.md`.

The current string slice supports selected prefix/suffix tests and trimming,
ASCII-only case conversion, literal splitting, and joining arrays or objects.
It does not implement regex-based splitting, Unicode case conversion, general
string interpolation, or nested array/object values in `join`.

Selected `type`, `tostring`, `tojson`, and single-value `fromjson` behavior is
also implemented. Full number formatting and jq's complete JSON parsing
semantics remain unverified.

Selected recursive `contains`/`inside` behavior and array `reverse` are
implemented and tracked separately in `STATUS.md`; this still covers only a
small portion of jq's built-in filters.

Selected `indices`, `index`, and `rindex` behavior is implemented for strings
and arrays, including overlapping matches and Unicode codepoint offsets. The
remaining receiver-type edge cases are only covered where `STATUS.md` says so.

Selected `length` behavior covers strings, arrays, objects, null, and numbers;
booleans fail. `flatten` supports arrays and object values with no depth or a
non-negative integer depth. Fractional depths fail explicitly and are outside
the current compatibility claim.

Selected `utf8bytelength`, `explode`, and `implode` behavior is implemented;
the finite Unicode and numeric boundary samples are listed in `STATUS.md`.

Selected `first`, `last`, `nth`, and `isempty` behavior covers array indexing and
finite output generators. The tested negative-index rules differ between array
indexing and generator selection; see `STATUS.md` for the exact sample boundary.

Selected `any` and `all` behavior covers direct iterable inputs, per-item
conditions, and explicit generator/condition pairs, with early termination on a
decisive result.


Selected `range` behavior covers the one-, two-, and three-argument forms,
ascending and descending integer/fractional sequences, and an empty result for a
zero step. This is a finite tested slice; argument streams and extreme numeric
precision remain limited as recorded in `STATUS.md`.


Selected `to_entries`, `from_entries`, and `with_entries` behavior covers
objects and arrays, documented entry-name aliases, key/value updates, and
filtering entries. These conversions remain a finite tested slice; exact error
messages and uncommon input combinations are not fully covered.


Selected `transpose` behavior covers rectangular and ragged arrays, empty rows,
and null rows; shorter rows are padded with null. Non-array rows fail in the
observed samples. See `STATUS.md` for the finite comparison and boundaries.


Selected `getpath` behavior covers nested object and array paths, comma-generated
multiple paths, missing values, negative and fractional indices, and null
interruption. Invalid path/component types fail in tested cases; see
`STATUS.md` for boundaries.


Selected `setpath` behavior covers nested creation, array extension with null,
negative indices, root replacement, and comma-generated paths that each update
the original input independently. Path and container errors are only checked
in the finite cases listed in `STATUS.md`.


Selected `walk(f)` behavior recursively transforms array elements and object
values before applying `f` to the containing value. The verified samples cover
bottom-up array sorting, nested scalar/object changes, and multiple filter
results inside arrays; see `STATUS.md` for the finite boundary.


Selected `recurse`, `recurse(f)`, and `recurse(f; condition)` behavior covers
depth-first traversal, explicit child generators, and condition-based stopping.
Unbounded output and recursion resource limits remain unverified; see
`STATUS.md` for boundaries.


Selected `path(expr)` and `paths` behavior covers exact field/index paths,
recursive container traversal, and predicate-filtered paths. Missing fields in
exact paths and array iteration are limited to the samples in `STATUS.md`.

Selected `delpaths(PATHS)` behavior removes multiple object keys and array
elements in one operation, using original array indices. Duplicate, nested,
missing, out-of-range, negative, and fractional-index cases are recorded in
`STATUS.md`; this remains a finite tested slice.

Selected SQL-style `INDEX`, `JOIN`, and uppercase `IN` behavior covers indexed
streams, the documented two/three/four-argument join forms, and one/two-stream
membership checks. Exact evaluation order and broader stream/error semantics
remain limited; see `STATUS.md`.

Selected `del(path_expression)` behavior removes exact, multi-value, and
iterator-selected paths simultaneously. Object fields, array indices, missing
paths, overlapping paths, and root deletion are only covered by finite samples
listed in `STATUS.md`.

Selected `pick(path_expressions)` behavior builds a sparse object/array from
the selected paths, filling missing values and array gaps with null. Its
supported path forms and remaining boundaries are listed in `STATUS.md`.

Selected `ceil`, `floor`, `round`, and `trunc` behavior covers finite numeric
inputs, negative values, halfway cases, and negative zero. Non-finite numbers,
extreme precision, platform math-library differences, and full jq compatibility
remain outside the verified scope; see `STATUS.md`.
