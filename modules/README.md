# PAH modules

This directory is reserved for Git submodules:

```text
modules/
├── code_analyzer/       → Code_Repository_Cataloguer
├── tech_documents/      → Research_Document_Workbench
└── reference_manager/   → Research_Paper_Repository_Manager
```

PAH 0.6 integrates all three through their public Python APIs, retains PAH-owned cross-module workflows, and can host each module's existing standalone web UI as a full work mode.

Do not copy module source into PAH. Use Git submodules and editable installs.
