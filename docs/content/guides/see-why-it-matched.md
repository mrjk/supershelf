# See why it matched

`supershelf scan inspect` prints how the match rules test kept files. It uses the same walk as `scan files --quick`: no hash, no mtime, and no ctime. The pattern order is in [Matching](../concepts/matching.md).

The path argument is the same as [List files](list-files.md). Omit it to print one line per kept file and no patterns. If any kept path equals the selector, every input traces that exact path only. Otherwise the selector traces each kept file whose path starts with it, with the same detail as a single file.

```bash
supershelf scan inspect
supershelf scan inspect "Bank2000/REL_20260425_ab12cd34.pdf"
```

Without a path, a hit looks like this:

```text
match profile books input 1 Bank2000/REL_20260425_ab12cd34.pdf rule bank2000_statement kind invoice
```

A miss looks like this:

```text
miss profile books input 1 notes/readme.txt
```

With a path, the default output prints each pattern that was actually tried, in rule and field order, and stops at the first hit:

```text
profile books input 1 rule bank2000_statement filename_regex 'REL_(?P<date>\d{8})_(?P<receipt_id>\w{8})\.pdf' against 'REL_20260425_ab12cd34.pdf': hit
Matched rule bank2000_statement kind invoice for Bank2000/REL_20260425_ab12cd34.pdf in profile books input 1
```

A value that no kept file has stops the command. The same relative path in two inputs is traced twice. Each line includes the profile and the input index.

## More detail

`-v` also prints the path, directory, and filename, skipped fields, captured groups, and a line when an earlier rule won so later rules were not tried.

A skipped field has no patterns, or it is a directory field and the file sits in the input directory:

```text
profile books input 1 rule bank2000_statement regex: skipped, no patterns
```

`-vv` also prints later patterns and later rules that matching never runs, marked `not tried`, with the candidate they would have used.

`-vvv` adds no extra inspect lines. Inspect writes these lines to stdout. The verbosity flags choose how many lines to print.

A bad pattern stops the command before the walk.

The next page stores values for a matched file: [Set variables](set-variables.md).
