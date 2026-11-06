# Names in ETF-row MUS files

The row adapter follows explicit references rather than matching strings in an
instrument palette. The field order is documented in Finale's ETF 98c.0 format
specification, under Staff Spec, Group Spec, Instrument Used, Text Block and Raw
Text. The specification is available in the upstream finale-file-parser research
documentation; it is not redistributed by this application.

* `IS` has a full-name reference at byte 30 and an abbreviated-name reference at
  byte 32. These are TX keys, not raw-text block numbers.
* `TX` contains four 12-byte incidences. Its first word selects `^block(n)` in
  the fourth, authoritative text pool. A TX key and a raw-text number may be
  completely unrelated. Never add a fixed offset or search a palette for a name.
* Two-incidence, 24-byte `Iu` slots carry the score's staff order. Accept that
  layout only when every staff is known and the list is unique. Unknown layouts
  retain the existing fallback order.
* `NG` carries group endpoints, name references and bracket style. Decode the
  documented 30-byte record and its 40-byte extension in the file's byte order.
  The score uses instrument-list key zero; other lists must not rename it.
* An unnamed staff may inherit the explicit name of an unambiguous two-staff
  brace. Its own nonempty name always takes precedence. Section brackets and
  conflicting braces are not used to infer instrument identities.
* Preserve the explicit `^flat()`, `^sharp()` and `^natural()` text inserts as
  Unicode accidentals before the upstream markup stripper runs.

The upstream IR and exporter remain responsible for musical events and MusicXML
groups. This change does not merge staff parts or infer instruments from pitches.
Individual part abbreviations are not yet exported by the upstream exporter.

The numeric-record zlib MUS layout has a different name-link representation and
does not gain speculative name recovery from this change. Unsupported references
still fall back to positional names. Generated tests cover unrelated reference
numbers, unused palette entries, both byte orders, both frame layouts, explicit
names, shared names, missing references and ambiguous groups.
