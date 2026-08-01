# Changelog

All notable changes to discord-server are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`pyproject.toml` holds the version and is the single source of truth for it.
Bump with `uv version --bump patch|minor` (or `alpha|beta|rc` for a
prerelease, `stable` to drop the tag). A MAJOR bump is the maintainer's call
and is never made automatically.

## [Unreleased]

### Added

- Tile race commands carry the event's elevated channel permissions, and a sync
  applies them to the channels that already exist. The team role's overwrite is
  reconciled with `set_permissions`, which replaces only that role's entry: a
  channel is never recreated, its history is kept, and an overwrite added by
  hand in Discord survives. An unchanged channel costs no API call.
- `pin_messages` uses Discord's own narrow permission (discord.py 2.7) rather
  than `manage_messages`, so a team can pin without also gaining the ability to
  delete each other's messages. `manage_messages` is its own toggle.

## [1.1.1] - 2026-08-01

### Security

- aiohttp 3.13.1 -> 3.14.3, pillow 12.1.1 -> 12.3.0, idna 3.11 -> 3.18 and
  python-dotenv 1.1.1 -> 1.2.2, clearing 49 Dependabot advisories. Lockfile
  only - no declared constraint moved, and `kaleido==0.2.1` / `plotly<6` are
  untouched, neither being a dependant of any upgraded package.
- setuptools stays at 75.9.1 against advisories GHSA-5rjg-fvgr-3xxf and
  GHSA-h35f-9h28-mq5c, which need 83.0.0. `upyloadthing 0.2.1` caps it at
  `<76.0.0` and is already the latest release, so the cap is upstream's. The
  high advisory is a path traversal in `PackageIndex.download`, reachable only
  when setuptools fetches from a package index, which this bot never does.

### Changed

- The valkey dependency drops its non-existent `asyncio` extra. valkey ships
  `valkey.asyncio` in the base package and provides only `libvalkey` and
  `ocsp`, so `valkey[asyncio]` resolved to the same thing while making uv warn
  on every lock.

## [1.1.0] - 2026-07-31

### Added

- Tile race Discord provisioning, driven entirely from the website's Controls
  tab over Valkey pubsub - the bot registers no slash commands for it. One
  category per event holds a captains channel plus a text and voice channel per
  team, each locked to that team's own role; members get their team role and
  captains get the captains role. Setup and re-sync run the same idempotent
  pass, so a team added after the first build is created on the next sync and a
  renamed team has its role and both channels renamed rather than rebuilt. Role
  membership is reconciled in both directions, so dropping someone from a roster
  on the site takes their channel access away instead of only granting it.
  Deleting one team removes just that team's objects, and teardown removes
  everything the event owns.
- The bot holds no tile race state of its own: every command carries the full
  desired shape and the resulting ids are POSTed back to api-backend with the
  shared service key. A run that fails part-way still reports what it managed to
  create, so a half-built event can be re-synced or torn down rather than
  leaving orphaned roles and channels nothing points at.

## [1.0.0] - 2026-07-28

Versioning baseline. The bot has been in production; 1.0.0 is adopted as the starting point rather than reconstructing its history.
