
# Subcommand implementation

## Import subcommand

The idea of the import is to scan an import folder, and process all files according rules. The result is stored in DB.


### import scan

List recursively all files in import dirs, and update the db:
* For each import_sources (from yaml config), do:
    * For each files, retrieve:
        * Get: dir_path, file_name, file_ext, file_sha256
    * Then update the db file_sources table:
        * Add new lines for each new files:
            * Unique identifier is the file hash, from file_sha256
            * add an import source name field (the one in the config)
            * Add other fields: dir_path, file_name, file_ext
            * Add a state field: (present|absent) 
            * Add created field, updated when the field is created
            * Add modified field, updated when the field is modified
        * Then look fo all other lines, and ensure the state is correctly set. If changes happen, update the last_modification field. Allowed modifications: import_source name field, file_name, file_path, file_ext, state

This command line must support the follwoing options:
--sources name1,name2,...: to only import a specific source instead of all
--files REGEX|GLOB: to only import files having a name matching a glob/regex
--dry|-n: Only log output, no modifications
--files: Only scan files, and stop here, no modifications

--db-add|--no-db-add: Scan files, and add to db
--db-cleanup|--no-db-cleanup: Update other lines

After the import scan, I expect to have the db syncronised from the content of the import directories. Never delete any lines or known hashes, this is an ever growing table.

### import sync

The goal of this comand is to run all import_rules on each files.


For each files, run the import rules:
* For each import_sources, do:
    * Build import rules: Assemble specific import_rules if any, and append generic import rules
* For each import_sources, do:
    * Fetch all files records matching the import_source
    * Check and apply import rules:
        * import_rules is a list, first match win
        * if a rule matched on patterns
            * Run the import driver on the file.
            * save the result in the data_sources table of the db:
                * Link to an existing files_sources (N:1) field:
                * add result of the driver output



This command line must support the follwoing options:
--sources name1,name2,...: to only import a specific source instead of all
--files REGEX|GLOB: to only import files having a name matching a glob/regex
--dry|-n: Only log output, no modifications

### import status

The goal of this command is to show the status of all files:



This command line must support the follwoing options:
--sources name1,name2,...: to only import a specific source instead of all
--files REGEX|GLOB: to only import files having a name matching a glob/regex


