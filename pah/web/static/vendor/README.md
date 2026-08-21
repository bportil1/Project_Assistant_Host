# Vendored editor assets

PAH's Workspace editor uses **Ace 1.44.0** from the official `ajaxorg/ace-builds`
`src-min-noconflict` distribution.

Run from the repository root:

```bash
python3 scripts/vendor_ace.py
```

The resulting `pah/web/static/vendor/ace/` directory is served locally by Flask.
PAH never loads Ace from a CDN at runtime. Release archives should include the
vendored directory so installation and normal use remain fully offline.
