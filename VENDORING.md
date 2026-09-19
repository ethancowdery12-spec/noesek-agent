# Vendored upstream source

Noesek vendors selected subsystems from NousResearch/hermes-agent (MIT, (c) 2025 Nous
Research) at pinned commit `c712f06dcdd24053a4118f38d2090ac53137ecfc` (2026-09-17,
v0.21.3). Vendored files are verbatim upstream except mechanical import-path rewrites
into the `noesek.vendor.hermes` namespace; each file carries a provenance header.
The upstream license text is at `src/noesek/vendor/hermes/LICENSE.hermes`.

Regenerate with `python3 scripts/vendor_hermes.py` after updating the pin.

## Manifest (SHA-256 of the upstream file at the pinned commit)

| Vendored path | Upstream path | Lines | Upstream SHA-256 |
| --- | --- | --- | --- |
| `noesek/vendor/hermes/utils.py` | `hermes-agent/utils.py` | 620 | `a9df1b33981ee6935696ab58b3bf4c12723d8431ed62aae6a55ae7bfabeba0f0` |
| `noesek/vendor/hermes/hermes_constants.py` | `hermes-agent/hermes_constants.py` | 1326 | `3c0b9d5d7b47318d1c9605a96719861059dd1ad80b4a696b215cf5fcf3d93ec7` |
| `noesek/vendor/hermes/hermes_time.py` | `hermes-agent/hermes_time.py` | 111 | `44867d31c4fcc09c248a9958f08c4ac57acf61cc9b20a9f2c8515c80de96ba69` |
| `noesek/vendor/hermes/tools/__init__.py` | `hermes-agent/tools/__init__.py` | 12 | `7bca460f476ac9ace706c8cfd07e98f8aae34d839862f0f68abafc3a8397cf35` |
| `noesek/vendor/hermes/tools/interrupt.py` | `hermes-agent/tools/interrupt.py` | 129 | `3127f53b4ca1431df828015a3eb06d29ffd43ea9b6a51954d3a45bc69483917b` |
| `noesek/vendor/hermes/tools/approval.py` | `hermes-agent/tools/approval.py` | 1336 | `070e2f8285b72689ad6e48cacd38770e2fa818622c68a5d2dc1bf5cdf52abfd8` |
| `noesek/vendor/hermes/tools/approval_context.py` | `hermes-agent/tools/approval_context.py` | 331 | `2ffc3f6792670ac4dd4c560284db13908b52102454cb4359a8275d10c7679b11` |
| `noesek/vendor/hermes/tools/approval_detection.py` | `hermes-agent/tools/approval_detection.py` | 1482 | `a6bb82b13d38c1bafe8a4a391d302004b03165e40e2c89b29fd2f8cda0b94d5d` |
| `noesek/vendor/hermes/tools/approval_floors.py` | `hermes-agent/tools/approval_floors.py` | 204 | `5b9af7c961926461382ff0c0f1193ad5b8dfbf7735a4bf8796855a055ff7c6d4` |
| `noesek/vendor/hermes/tools/approval_gateway_wait.py` | `hermes-agent/tools/approval_gateway_wait.py` | 206 | `5973b3a3ca3aa10d89bee27cbb8e73d725e6f285ad57619d2d6eab3218003f24` |
| `noesek/vendor/hermes/tools/approval_human_wait.py` | `hermes-agent/tools/approval_human_wait.py` | 169 | `36a54842802456364fbe9b68cb3598b21bf295d7b0fd9bdb42b63350864cad6f` |
| `noesek/vendor/hermes/tools/approval_prompt.py` | `hermes-agent/tools/approval_prompt.py` | 336 | `aea5a523459bc3f4ce9da8676915bd6637d41e9ae304c7e964c3113ba69cd8f1` |
| `noesek/vendor/hermes/tools/approval_smart.py` | `hermes-agent/tools/approval_smart.py` | 145 | `86ce2f7c27bc1b350f715a0d9a5d9ed39befd5295193c02d3765aa47e6efa3e8` |
| `noesek/vendor/hermes/cron/occurrences.py` | `hermes-agent/cron/occurrences.py` | 103 | `f77d786e7445cb4c6517151ae5184deb284295377991a95d3b9735de35cfcbda` |
| `noesek/vendor/hermes/cron/executions.py` | `hermes-agent/cron/executions.py` | 375 | `1c7af4651cece5cdd8995464ba5d18c88a3b9c23cfceed757626b73c01e06535` |
| `noesek/vendor/hermes/cron/incidents.py` | `hermes-agent/cron/incidents.py` | 268 | `4c137d451903b89bd9fdd4048d8694cd268bcceab4cdc65ac196c817b13b8b60` |
| `noesek/vendor/hermes/cron/delivery_queue.py` | `hermes-agent/cron/delivery_queue.py` | 386 | `27dd524eecdcaa48f0932a0fbc6b067451f8bcf060a2c1b7bee7fdf02cbc74c2` |
| `noesek/vendor/hermes/tools/ansi_strip.py` | `hermes-agent/tools/ansi_strip.py` | 83 | `71f339d1be720c24f407565b4a90cb55164dead2e860cf438258104fd96c1922` |
| `noesek/vendor/hermes/agent/retry_utils.py` | `hermes-agent/agent/retry_utils.py` | 165 | `9963eca069424da8cf08e896b4fd338fc0f47e1120496e0b10fbf62e4c09b608` |
| `noesek/vendor/hermes/hermes_cli/sqlite_util.py` | `hermes-agent/hermes_cli/sqlite_util.py` | 113 | `1ffde9d5e896dee3282514c81676d00d7535c833fc6d5ef9c43a42ae3778de79` |
| `noesek/vendor/hermes/hermes_cli/sqlite_runtime.py` | `hermes-agent/hermes_cli/sqlite_runtime.py` | 94 | `8ca58b7997fa8afd097d92198c0e6040277f4b03ef87432a76c2358fd881a5cc` |
| `noesek/vendor/hermes/hermes_state_wal.py` | `hermes-agent/hermes_state_wal.py` | 646 | `a1f960a4ff85c6854139966edd96eb20056a0578eb1c901572f91e164bfa94be` |
| `noesek/vendor/hermes/cron/jobs.py` | `hermes-agent/cron/jobs.py` | 3445 | `0e444b6ce34f7dde94374e6826c07f69e4854a2eb160efad728838469a1d30ad` |
| `noesek/vendor/hermes/cron/env_settings.py` | `hermes-agent/cron/env_settings.py` | 26 | `ac9e78792160cd0541d0979e53259ddfc48cb6c40bf7a23599e783abcd7a2574` |
| `noesek/vendor/hermes/cron/notepad.py` | `hermes-agent/cron/notepad.py` | 166 | `1325b3bcd8a8e17ab80ce52656bb1cf7988414f7db9e8cd3364c0de1644a15a0` |
| `noesek/vendor/hermes/cron/unreachable_retry.py` | `hermes-agent/cron/unreachable_retry.py` | 125 | `ae75a7e3371e7b601f1265e5e87dfcecfa93e93ada257f45879246256ea21378` |
| `noesek/vendor/hermes/agent/skill_utils.py` | `hermes-agent/agent/skill_utils.py` | 811 | `bdf333b572f13f0868c570e31254073864139c5e87fc56c5245b19100080c5ac` |
| `noesek/vendor/hermes/tools/path_security.py` | `hermes-agent/tools/path_security.py` | 41 | `e7f2d8c382b0333d3b937f08e1f0ec4ca455926dea43f6c70ca83ea11d62eed0` |
| `noesek/vendor/hermes/tools/skills_tool.py` | `hermes-agent/tools/skills_tool.py` | 743 | `fd07caf04fee568496576cd10d6be735108fe348b22d737a17aeb01fe99c7334` |
| `noesek/vendor/hermes/tools/skills_tool_dedup.py` | `hermes-agent/tools/skills_tool_dedup.py` | 90 | `205e324ceb338a908616adda7698eeb0c5c89ebbd25a1bbef62d3b6e53124b3a` |
| `noesek/vendor/hermes/tools/skills_tool_plugin.py` | `hermes-agent/tools/skills_tool_plugin.py` | 172 | `59a4de0cffcf4991027d24fbebc68e35978badc3c0dc929a07cf954e4dc2335a` |
| `noesek/vendor/hermes/tools/skills_tool_setup.py` | `hermes-agent/tools/skills_tool_setup.py` | 150 | `afcbbfba8c5c4dfc796b5ea13a9a2cc4cb215a3c45e3d66521fd657cd3aca73c` |
| `noesek/vendor/hermes/tools/skill_ledger.py` | `hermes-agent/tools/skill_ledger.py` | 415 | `8a7d46d2fc21b916a211788ad16f4d2c9b8990e5af1374fba4f57d1618bd9060` |
| `noesek/vendor/hermes/tools/skill_provenance.py` | `hermes-agent/tools/skill_provenance.py` | 44 | `5c492a925cdde61c3257eb5db76568822d26be3d9a2c40d364a9997a3a7cb576` |
| `noesek/vendor/hermes/tools/skill_usage.py` | `hermes-agent/tools/skill_usage.py` | 763 | `33a62bd3cbb394918f58e797d05071d18b9af1786ec9d96541579a9e2ba98718` |
| `noesek/vendor/hermes/tools/skills_guard.py` | `hermes-agent/tools/skills_guard.py` | 811 | `1cf00dcb85faeab6fbd8a68ffabaf518be359326508c6e20bb444e0f7f60db37` |
| `noesek/vendor/hermes/tools/skill_linter.py` | `hermes-agent/tools/skill_linter.py` | 219 | `8a5d4d4033ad33195bc9dc31ecb78b0bbea85f51af2126d7d482c5b7c0517148` |
| `noesek/vendor/hermes/tools/registry.py` | `hermes-agent/tools/registry.py` | 977 | `389b5f8bd9d8b87c56895074cf5c61a12c91c7476fe0cf932c9959c216f8b8ab` |
| `noesek/vendor/hermes/gateway/config.py` | `hermes-agent/gateway/config.py` | 837 | `c56a181c2d7c1c03b4f2d8a555877bf090fa324ebaba9b3b58f06f4b62389582` |
| `noesek/vendor/hermes/gateway/config_loader.py` | `hermes-agent/gateway/config_loader.py` | 424 | `da80efbf277872857f709833ccdff1876ab06819dd5829a44c46b3618169f729` |
| `noesek/vendor/hermes/gateway/channel_directory.py` | `hermes-agent/gateway/channel_directory.py` | 473 | `8d33ef9778a0e2fd265f57ef7bdfb7ffa5b83f91d200cdec64eb0197218fd497` |
| `noesek/vendor/hermes/gateway/shutdown_watchdog.py` | `hermes-agent/gateway/shutdown_watchdog.py` | 380 | `507b42c41eb280fd854b3764ea03d4d8653fce2881432f4b0985461a2b69c024` |
| `noesek/vendor/hermes/plugins/__init__.py` | `hermes-agent/plugins/__init__.py` | 1 | `afceb915688f3d01bec6cc3290d83159534c0939edb05775d24a54afb35353dc` |
| `noesek/vendor/hermes/plugins/plugin_loader.py` | `hermes-agent/plugins/plugin_loader.py` | 182 | `2fd4cf63b3649c23d6f8950c3ab62cc0a4ea9910254e986b6e67e1a584b2396d` |
| `noesek/vendor/hermes/plugins/plugin_storage.py` | `hermes-agent/plugins/plugin_storage.py` | 46 | `97a396933dab9e8f3a2d3bf1d437881c5d2677cd2c0e993f05c681d489a7c758` |
| `noesek/vendor/hermes/plugins/plugin_utils.py` | `hermes-agent/plugins/plugin_utils.py` | 64 | `e8a7595f6e9eb696670a91019f81213551ed66096c119035d1788c44a1fc9456` |
| `noesek/vendor/hermes/gateway/whatsapp_identity.py` | `hermes-agent/gateway/whatsapp_identity.py` | 96 | `bcd593d3f0bc9374984ef71061ca255998dd9cbe0b7adb02e5c8b525910a54d8` |
| `noesek/vendor/hermes/gateway/bot_loop_guard.py` | `hermes-agent/gateway/bot_loop_guard.py` | 141 | `3175badf27025f3dd2a26c930511853d174f5e0a18e599a3b38f8fe16b08e0a5` |
| `noesek/vendor/hermes/gateway/pairing.py` | `hermes-agent/gateway/pairing.py` | 617 | `d331960bb2f9053ca4597bdda61e73383d68827ce1a4c0e225181945067011a2` |
| `noesek/vendor/hermes/gateway/authz_mixin.py` | `hermes-agent/gateway/authz_mixin.py` | 667 | `f3f605e42bc835a5a162ae55e8f693137238941322902d9ebca3df82a949bdba` |

## Noesek-authored bridge modules (NOT upstream source)

These let the vendored code run inside Noesek's configuration and policy stack:

- `hermes_cli/config.py` - cfg_get / load_config_readonly / load_config / get_hermes_home,
  deny-by-default; save_config refused; owner-only file/dir permission helpers
- `hermes_cli/config_effective.py` - empty effective config
- `hermes_cli/plugin_compat.py` - one-shot deprecation warnings
- `hermes_cli/plugins.py` - no Hermes plugin discovery (Noesek registry owns plugins)
- `hermes_cli/auth.py` - no Hermes secret store
- `hermes_cli/managed_scope.py` - passthrough scope
- `agent/redact.py` - secret scrubber for the delivery queue
- `agent/secret_scope.py` - no multiplexing; plain .env reader; UnscopedSecretError
- `agent/monitoring/cron_health.py` - execution-state heartbeats -> trace log
- `agent/delegation_context.py` - no dispatcher-owned worker context
- `agent/runtime_cwd.py` - terminal cwd via process env
- `agent/terminal_env_registry.py` - no provider env flags
- `agent/skill_preprocessing.py` - skill template preprocessing passthrough (tranche note)
- `gateway/status.py` - POSIX pid liveness / start time
- `gateway/session_context.py` - session env via process env
- `gateway/restart.py` - verbatim upstream restart exit-code constant
- `gateway/platform_registry.py` - empty registry (Noesek channel layer owns platforms)
- `gateway/profile_routing.py` - no profile routing
- `gateway/platforms/base.py` - verbatim upstream secret-capture message constant
- `gateway/platforms/_shared.py` - literal decoding / env helpers, inert scoping
- `gateway/platforms/helpers.py` - no Discord platform
- `tools/kanban_tools.py` - no kanban toolset
- `tools/skill_manager_guards.py` - background-review marker no-op
- `tools/terminal_scope.py` - terminal env via process env
- `tools/budget_config.py` - upstream default result-size constant (100_000)
- `cron/__init__.py` - package init (upstream's imports the full scheduler)
- `cron/scheduler.py` - empty in-process running-set (Noesek's tick + task runner executes)
- `cron/scheduler_preflight.py` - verbatim port of upstream's transient provider-error classifier
- `cron/lifecycle_guard.py` - no Hermes gateway daemon: never matches
- `gateway/session.py` - verbatim port of upstream SessionSource + _CHAT_TYPE_PREFIX (lines 60-161); SessionStore mixins not vendored
- `gateway/run.py` - logger + always-None in-process runner reference
