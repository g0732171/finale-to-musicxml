# Contributing

- Run `python -m unittest discover -s tests -v` after converter or application changes.
- Use generated fixtures or files you have permission to share. Never commit client
  scores, local paths, tokens, conversion results, or a private regression corpus.
- Prefer verified format rules over filename/version-specific exceptions. A known
  version banner is not proof that its record layout is supported.
- Preserve active music references. Reject unknown critical layouts rather than
  dropping a bad frame and returning a deceptively valid fragment.
- For musical changes, compare against an independent MusicXML export where possible;
  successful parsing or schema validation alone does not establish musical fidelity.
- Keep native picker tests mocked or manual. Public automated tests must not open
  desktop windows. Document actual OS/UI tests separately from headless CI.
- Preserve upstream copyright notices and explain which project supplied an adapted
  decoder. New dependencies need their license notices in the source/build outputs.
