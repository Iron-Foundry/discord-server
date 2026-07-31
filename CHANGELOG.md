# Changelog

All notable changes to discord-server are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`pyproject.toml` holds the version and is the single source of truth for it.
Bump with `uv version --bump patch|minor` (or `alpha|beta|rc` for a
prerelease, `stable` to drop the tag). A MAJOR bump is the maintainer's call
and is never made automatically.

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
