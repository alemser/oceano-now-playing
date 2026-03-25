# Prompt para AI no Novo Projeto

Use o texto abaixo na nova janela do projeto.

---

Contexto:
Este repositorio e um fork de spi-now-playing e deve ser convertido para uma versao Oceano-only, integrada ao projeto oceano-player (Go). O objetivo e manter o app de display em Python, lendo metadata do shairport-sync via FIFO, e remover suporte a outros media players.

Objetivo principal:
Refatorar o projeto para funcionar apenas com Oceano, com codigo, testes e documentacao coerentes com esse escopo.

Requisitos tecnicos:
1. Manter renderer e state machine existentes.
2. Manter `OceanoClient` como unica fonte de estado.
3. Remover runtime paths de Volumio, Moode e piCorePlayer.
4. Simplificar configuracao para Oceano-only (especialmente `OCEANO_METADATA_PIPE`).
5. Atualizar testes para refletir o novo escopo.
6. Atualizar README, scripts e metadados de pacote.

Arquivos prioritarios para alterar:
- `src/app/main.py`
- `src/config.py`
- `src/media_players/__init__.py`
- `pyproject.toml`
- `README.md`
- `tests/test_media_player.py`
- `tests/test_config.py`
- Remocao/ajuste de suites antigas: `tests/test_volumio.py`, `tests/test_moode.py`, `tests/test_picore_player.py`

Regras de implementacao:
1. Fazer mudancas incrementais com commits pequenos.
2. Rodar testes a cada etapa relevante.
3. Nao introduzir regressao no fluxo Oceano e no renderer.
4. Preservar comportamento de tratamento de metadata incompleta (Unknown, grace period, timeouts).
5. Garantir type hints e docstrings consistentes com padrao do projeto.

Plano de trabalho solicitado para esta execucao:
1. Apresentar plano curto de 5-8 passos.
2. Implementar Fase 1 (runtime Oceano-only) completa.
3. Ajustar testes necessarios para Fase 1.
4. Executar suite de testes e reportar resultados.
5. Atualizar README minimo para refletir novo escopo.
6. Entregar resumo final com arquivos alterados e proximos passos.

Critério de sucesso desta rodada:
- App executa com caminho Oceano-only.
- Testes relevantes passam.
- Documentacao minima atualizada.

---

Se houver duvidas de naming, adote provisoriamente:
- nome do projeto: `oceano-now-playing`
- branch base de trabalho: `fork/oceano-only-bootstrap`
