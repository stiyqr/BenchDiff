# Kickoff prompt

One session per phase. Paste this as the first message, editing the three `{}` spots.

> Phase {N-1} is done and committed. Read `AGENTS.md`, `docs/vision.md`, `docs/decisions.md` and
> `docs/phase-{N}.md`.
>
> We are building phase {N}, and I am writing the code myself. Follow the working agreement in
> `AGENTS.md`: you explain and review, I type. Do not create or edit files unless I ask you to, and
> never run git commands that change anything.
>
> Start with build-order step {k}, `{module}`. Tell me what it has to do, its public shape, the test
> rows it owns and the choices I need to make. Then stop — one step per exchange.
>
> Note: `uv` is not on PATH in your shell. It is at
> `C:\Users\lukit\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.

## Phase 1 instance

> Phase 0 is done and committed. Read `AGENTS.md`, `docs/vision.md`, `docs/decisions.md` and
> `docs/phase-1.md`.
>
> We are building phase 1, and I am writing the code myself. Follow the working agreement in
> `AGENTS.md`: you explain and review, I type. Do not create or edit files unless I ask you to, and
> never run git commands that change anything.
>
> Start with build-order step 2, `errors.py`. Tell me what it has to do, its public shape, the test
> rows it owns and the choices I need to make. Show me signatures and a skeleton, not a finished file.
> Then stop — one step per exchange.
>
> Note: `uv` is not on PATH in your shell. It is at
> `C:\Users\lukit\AppData\Local\Microsoft\WinGet\Packages\astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe\uv.exe`.

## If it drifts

Agents default to doing. If it starts writing files, stop it with:

> Stop. Per `AGENTS.md`, explain the shape and let me write it. Ask before touching any file.

If it commits, that is a rule break, not a favour — the working agreement is explicit that it must
not run `git add`, `commit` or `push`.
