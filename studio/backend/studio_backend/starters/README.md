# Language starters

What a new bot (빈 상담봇 or 복사) gets for its language: the situation wording of `notices.yaml` (no fixed notices) and the
confirm, command, correction and confusion words under `rules/`. These are about the language, not the business: the
three domains in `domains/` hold the same text per language, and these files were taken from them. The engine's loader
needs all of them once a bot has `rules/config.yaml` (`voxstage/domain_pack.py`, `DomainPack.load`).

One directory per language of the engine (`voxstage/dataset.py` `LANGS`); `test_bots.py` checks that every engine
language has a starter and that an empty bot built from it passes validation.
