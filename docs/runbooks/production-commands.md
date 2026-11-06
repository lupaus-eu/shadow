# Production commands (`make`)

[`Makefile.prod`](../../Makefile.prod) gives the production host short commands for
the Compose work. Run them in `/opt/yearclock` as the `deploy` user. Every command
reads `docker-compose.prod.yml` and `.env.production`; `make help` lists them.

## Install

The file is not used in development (there the `Makefile` is the local one). Copy it
to the host under the name `Makefile`, from your own machine, and again whenever it
changes:

```bash
rsync -av Makefile.prod hetzner-deploy:/opt/yearclock/Makefile
```

`make` itself comes from cloud-init; on an older host: `sudo apt-get install -y make`.

## Everyday: release and status

| Command | What it does |
| --- | --- |
| `make deploy` | Downloads the images named by `YEARCLOCK_TAG`, starts or updates the stack, and shows the status. The normal way to release. |
| `make tag TAG=sha-1234567` | Writes the release into `YEARCLOCK_TAG` in `.env.production` (letters, digits, `.`, `_`, `-` only). It changes nothing that runs; follow it with `make deploy`. A rollback is the same with the previous tag. |
| `make version` | Shows the configured tag and the image and status of every service. |
| `make ps` | Shows the services, including finished one-shot containers (`migrate` should be `exited (0)`). |
| `make logs` | Follows the last 100 lines of every service's log. `make logs SERVICE=backend` follows one. Stop with Ctrl+C. |
| `make stats` | Shows memory and CPU use per container, then the host's memory and disk. Look here when the host feels slow. |

A release in two commands:

```bash
make tag TAG=sha-1234567
make deploy
```

## Parts of the cycle

| Command | What it does |
| --- | --- |
| `make config` | Checks that the Compose file and `.env.production` resolve (a missing required value fails here). Starts nothing. |
| `make pull` | Only downloads the images. |
| `make up` | Only starts or updates the stack from the images already downloaded. |
| `make restart SERVICE=backend` | Restarts one service. `SERVICE` is required. |
| `make down` | Stops and removes the containers. Data volumes stay, so nothing is lost. |

## Administration

| Command | What it does |
| --- | --- |
| `make authentik-apply` | Applies the Authentik blueprints now, even when nothing changed. Normally `authentik-config-init` skips them and the apply happens only when a blueprint, the Authentik image, or a related setting changed (`authentik-invitations.md`). Use it to undo a change made in the Authentik interface. |
| `make enroll-platform EMAIL=you@example.com ROLE=platform_admin` | Allows that address to sign in to the Platform area (`ROLE` is `platform_admin` or `support_agent`). Run it before the person's first Platform sign-in, and never sign that identity in to the customer application first. Needs the stack to be running. |
| `make backup` | Runs the off-host backup once, now (`backup.md`): dumps both databases, copies them to Scaleway with restic. Needs the `BACKUP_*` settings. |
| `make timers` | Shows the `yearclock-*` systemd timers and when they last and next run. Empty until the timers are enabled after the backup is set up. |

## Housekeeping

| Command | What it does |
| --- | --- |
| `make prune` | Deletes images no container uses. Run it now and then, since every release leaves the previous images on the disk. |

## Good to know

- `make up` and `make deploy` are safe to repeat: the one-shot containers
  (`migrate`, `authentik-config-init`) are idempotent and finish in seconds when
  there is nothing to do.
- A Compose command behind a target is printed before it runs, so you can copy it
  when you need to vary it. `ENV_FILE=other.env make config` uses another env file.
- The commands that change the release or the environment (`tag`, `down`, `prune`)
  do not ask for confirmation.
