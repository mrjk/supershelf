# Supershelf

Supershelf loads one or more profile files, walks their input directories, matches each kept file to a kind, and prints the variables for that file.

A profile is a TOML or YAML file. It names the folders to read, the rules that classify files, and the values to attach to each match. The scan commands print that result. This version does not write an output tree, a database, or a cache file. See [Limits](concepts/limits.md).
