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
