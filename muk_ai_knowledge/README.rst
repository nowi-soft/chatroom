MuK AI Knowledge
================

Adds a persistent knowledge base (``muk_ai.knowledge``) that can be linked to
``muk_ai.agent`` records via many-to-many. Two injection modes:

- **inline**: concatenated into the agent's system prompt at session build
  time.
- **tool**: exposed via a ``search_knowledge`` tool the agent can call on
  demand.

Supports text/HTML/file content with extraction for PDF, DOCX, XLS/XLSX, TXT,
MD, CSV.
