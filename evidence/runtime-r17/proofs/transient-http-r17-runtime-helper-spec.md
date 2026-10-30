---
title: 'R17: безопасная проверка и переключение существующего canary'
type: 'bugfix'
created: '2026-10-30'
status: 'in-review'
review_loop_iteration: 0
baseline_commit: 'd45ee450b4a9ab1d49bb045ae1b1a8224f5be131'
context: []
---

Источник цели, ownership и DONE: CrewSync, task `bifrost-canary:runtime-helper-repair-r17`, note `:spec`. Этот файл — проекция для Quick Dev, не отдельный план. Точный scope уже утверждён пользовательским handoff и MANAGED_GO v4.4; повторное согласование неизменной задачи не требуется.

<frozen-after-approval reason="existing user-approved MVP runtime gate">

## Intent

**Problem:** Принятый исходный SHA и проверенный бинарник ещё не прошли реальный isolated E2E, rollback и активацию. Старый activation-helper связан с устаревшей QA и недоказанным pause; старый probe привязан к живому порту.
**Approach:** Завершить три существующих/запланированных конечных helper-файла, проверить их отрицательные случаи, затем передать координатору для отдельных runtime gates.

## Boundaries & Constraints

**Always:** Привязать SHA d45ee450b4a9ab1d49bb045ae1b1a8224f5be131, native QA_ACCEPT, build metadata/хеш бинарника и 29-case fixture. Только loopback. Хранить реальную историю native Goals и провалившихся turn. Не повторять неоднозначный POST. Сначала копия конфигурации, проверка PID/creation/path/hash, отсутствие активных запросов; затем контролируемое переключение. Реальный rollback должен пройти SSE probe.
**Ask First:** Действия вне изолированного canary, изменение глобальной маршрутизации или новый сервис.
**Never:** Изменять Go/Git HEAD, OpenCodex, глобальную конфигурацию; новый scheduler/daemon; force push; ложные pause/QA/DONE; общий writable app-dir для rehearsal.

## I/O & Edge-Case Matrix

| Сценарий | Вход | Результат | Отказ |
|---|---|---|---|
| SSE | Явный port, response.completed со status completed и sentinel | PASS, один POST | Неуспешный status, error/failed, неверный sentinel — FAIL |
| Proof | Точные SHA, QA/report hashes, toolchain/dependency/build, 29 PASS | Runtime gate открыт | Любое несовпадение закрывает gate до запуска |
| Rehearsal | Private app-dir, свободный port | Candidate SSE; остановка; old SSE на том же port; cleanup | Только собственные Popen; live runtime неизменен |
| Drain | Несколько нулевых expected metrics и отсутствие Established | Разрешить stop после последней identity/drain проверки | Нет series/появилась нагрузка/другой owner — отказ |
| Activation fault | Candidate не проходит readiness/SSE | Восстановить old EXE/config и проверить SSE | Чёткий FAIL, сохранённый receipt, без повторного POST |

</frozen-after-approval>

## Code Map

- `../probe_transient_http_r14_live.py`: validate_sse(status, raw, sentinel), probe(port, sentinel, timeout); частичная native-реализация сохранена.
- `../activate_transient_http_r14.py`: существующие identity/listeners/metrics/launch/stop_owned/live и proof gates. Общие функции можно импортировать без эффектов.
- `../rehearse_transient_http_r17.py`: конечный CLI, использующий те же функции запуска/проверки/остановки.
- `../evidence/transient-http-r17-runtime-helper-*`: backup, проверяемый manifest и fake/local tests.
- Build/fixture/helpers конфигурации и Go-исходники вне write scope.

## Tasks & Acceptance

**Execution:**
- [x] Probe: обязательный port и terminal payload status — сохранён результат native child; требуется проверка.
- [x] Activation: новые immutable gates, доказанный drain, проверяемый rollback и честные receipts.
- [x] Rehearsal: private app-dir, тот же isolated port, обе SSE-проверки, конечный cleanup.
- [x] Локальные отрицательные proof/parser/lifecycle tests, syntax, независимая проверка digest snapshot.

**Acceptance Criteria:**
- Given неверный SHA/QA/report/binary/helper hash, when вызван gate, then нет запуска/остановки процесса и возвращён FAIL.
- Given корректно закрытый SSE с неуспешным terminal status, when parser проверяет ответ, then PASS невозможен.
- Given сбой candidate, when выполняется rehearsal/rollback, then остановлены только собственные children, старый EXE проверен через тот же isolated port.
- Given live baseline до rehearsal, when завершён cleanup, then исходные PID/creation/config/global hashes сохранены и isolated port свободен.
- Given нагрузка, отсутствие expected series или иной owner, when activation проверяет drain, then старый процесс не остановлен.
- Given helper candidate, when независимый Reviewer проверяет точные hashes и meaningful tests, then только его QA_ACCEPT разрешает реальные runtime gates.

## Spec Change Log

- Native Luna child 01a18e3f-67ea-7851-9f67-38068920775d завершил turn failed429 после backup/probe; Goal blocked. Manager 01a18bb3-ad16-7162-bfa4-2a559c14d419 сверил результат и paused. Координатор принимает оставшийся scope без повторного исполнителя и без стирания accounting. Функциональные критерии сохранены.

## Design Notes

Activation содержит общие функции с guard main. Rehearsal импортирует их, но владеет собственными Popen и private app-dir. Никакого resident scheduler; для рабочего canary сохраняется существующий жизненный цикл родительского launcher. QA по digest snapshot helper-файлов отделена от ранее принятой QA исходников d45ee450.

## Verification

- `python -m py_compile ../probe_transient_http_r14_live.py ../activate_transient_http_r14.py ../rehearse_transient_http_r17.py` — syntax PASS.
- `python ../evidence/transient-http-r17-runtime-helper-tests.py` — fake/local parser/proof/lifecycle guards PASS без реального провайдера.
- До завершения независимой проверки runtime entrypoints не запускать.
