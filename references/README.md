# References

Put NASA reference texts here as `.md` or `.txt` files for the assistant.

- One topic per file, with the original title and source URL written at the top of the file (as text; the app never opens it).
- Only public, citable material (e.g. NASA technical reports, the Human Research Program evidence reports).
- The assistant (`server/features/assistant/`) will index this folder locally with `nomic-embed-text` through Ollama and cite the file in its answers.
- Thresholds in `config/thresholds.yaml` should cite a file in this folder in their `source` field.
