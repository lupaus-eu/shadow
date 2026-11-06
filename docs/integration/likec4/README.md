# Yearclock × eTWIN concept model (LikeC4)

A separate LikeC4 model, kept apart from `docs/architecture/c4` (the Yearclock C4 model) until the
integration design is settled. Companion to `../yearclock-etwin-spec.md`.

- Amber = Yearclock concepts, indigo = eTWIN concepts.
- Cross-system arrows are all **proposals**: red = plan to model, green = model back to plan,
  slate = alignment by reference. Each one is explained in a comment and description in `model.c4`.

```bash
npx --yes likec4@1.59.4 validate docs/integration/likec4
npx --yes likec4@1.59.4 start --port 8177 docs/integration/likec4
```

Port 8177 is within the Yearclock range (8100–8199) but not yet recorded in
`docs/architecture/docker.md`; record it there if this becomes a standing command.
