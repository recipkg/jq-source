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
