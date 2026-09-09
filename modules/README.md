# PAH modules

This directory is reserved for Git submodules:

```text
modules/
├── code_analyzer/       → Code_Repository_Cataloguer
├── pypique/             → pyPIQUE
├── hsqa_dbn/            → HSQA_DBN
├── tech_documents/      → Research_Document_Workbench
└── reference_manager/   → Research_Paper_Repository_Manager
```

PAH keeps independently runnable research tools as submodules and installs them editable into the host environment. Code Analyzer, pyPIQUE, and HSQA_DBN form the current Code Analysis Lab provider set; Documents and References remain separate host services.

Do not copy module source into PAH. Use Git submodules and editable installs.

The canonical provider submodules are `git@github.com:bportil1/pyPIQUE.git` and `git@github.com:bportil1/HSQA_DBN.git`. Their gitlinks are owned by PAH and should be updated through the normal Git submodule workflow.
