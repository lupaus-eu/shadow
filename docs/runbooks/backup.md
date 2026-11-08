# Off-host backups

Both PostgreSQL databases (Shadow and Authentik) are dumped on a schedule,
encrypted on the host with [restic](https://restic.net/), and stored in Scaleway
Object Storage. A failed backup, and optionally every successful one, sends an email
through the Scaleway Transactional Email service the application already uses; an
external heartbeat service is optional. Nothing here runs
until an operator does the setup below; the scripts live in `scripts/ops/`.

| Phase | Frequency | Target |
| --- | --- | --- |
| Alpha | daily at 03:15 | recovery point of one day |
| Beta | hourly | recovery point of one hour, recovery time of half a day (`beta-launch.md`) |

## How it works

`scripts/ops/backup-offsite.sh`:

1. dumps both databases with `backup-databases.sh` into `/var/backups/shadow`;
2. adds the dumps and `.env.production` itself (`BACKUP_EXTRA_FILES`) to a
   restic repository in the bucket, encrypted with the repository password;
3. keeps 24 hourly, 30 daily, and 6 monthly snapshots (`forget --prune`);
4. checks the repository and deletes local dumps older than two days. A failure sends
   an email to `BACKUP_ALERT_EMAIL`; with `BACKUP_SUCCESS_EMAIL=true` every success
   does too, so a missing daily email is itself the signal that the backup did not
   run. If `BACKUP_HEARTBEAT_URL` is set, it also pings that URL (optional, see
   "Alerts").

Restic encrypts before upload: the bucket never holds readable data, and the
operator alone holds the key.

## Set up (once)

1. **Bucket.** In the Scaleway console create a private Object Storage bucket in
   **project of its own**, separate from the host's project, so an account mix-up
   cannot reach both. The same region as the host is fine for the alpha; a bucket in
   another region also survives a regional outage (consider it for the beta). Turn on **versioning**, and add a lifecycle
   rule that expires non-current versions after about 35 days so deleted data
   does not accumulate forever. Check both in the console; versioning keeps a
   copy if a script or a stolen key deletes objects.
2. **Access key.** Use a Scaleway project of its own for the backups, with an IAM
   application and API key that can read and write only this bucket (the policy
   needs read access to the bucket and read, write, and delete of objects; check
   the exact permission names in the console). Restic needs delete rights for
   pruning, so versioning is the protection against misuse. The values follow the
   project's shared Scaleway convention (`SCW_ACCESS_KEY`, `SCW_SECRET_KEY`,
   `SCW_DEFAULT_ORGANIZATION_ID`, `SCW_DEFAULT_PROJECT_ID`, see
   `docs/architecture/email.md`) with a `BACKUP_` prefix, so the backup's project
   does not collide with the email settings. Restic talks to the object storage
   with the S3 protocol, which uses only the key pair, the bucket, and the region;
   the organization and project IDs are stored with the rest for the convention,
   not sent by restic.
3. **Install restic** on the host (`apt install restic`, or the release binary).
   Alerts need no new account: they use the email settings (`SCW_*`) already in
   `.env.production`.
4. **Repository password.** Create the restic password and keep it **outside
   the host**: in the password manager and on paper in a safe place. Without it
   the backups cannot be read.

   ```bash
   openssl rand -base64 32     # copy the result to the password manager
   ```

5. **Settings in `.env.production`.** The backup scripts read the same
   `.env.production` file the production stack already uses (in the project
   directory on the host, for example `/opt/shadow/.env.production`); there is no
   separate backup file. Add these lines to it, with real values, and keep it
   `chmod 600`:

   ```bash
   BACKUP_SCW_BUCKET=<bucket name>
   BACKUP_SCW_REGION=fr-par
   BACKUP_SCW_ACCESS_KEY=<access key of the backup project's API key>
   BACKUP_SCW_SECRET_KEY=<its secret key>
   BACKUP_SCW_DEFAULT_ORGANIZATION_ID=<organization ID>
   BACKUP_SCW_DEFAULT_PROJECT_ID=<ID of the backup project>
   RESTIC_PASSWORD=<the repository password from step 4>
   BACKUP_ALERT_EMAIL=<where alerts are sent>
   BACKUP_SUCCESS_EMAIL=true
   ```

   `BACKUP_SCW_REGION` is the region of the bucket (`fr-par` for Paris; the scripts
   have no default, so a missing value is an error).

   The database settings the dump needs (`POSTGRES_USER`, `POSTGRES_DB`,
   `AUTHENTIK_POSTGRES_*`) are already in the file. Optional settings, all with
   defaults, are listed in `.env.production.example`. Write each value as plain `KEY=value`; the
   scripts read the file line by line and do not expand `${VAR}` or trailing
   comments. Docker Compose ignores the extra lines.
6. **Timers.**

   ```bash
   sudo cp scripts/ops/systemd/*.service scripts/ops/systemd/*.timer /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable --now shadow-backup.timer shadow-disk-check.timer
   ```

7. **First run.** Run it by hand, check that the success email arrives, and look at
   the snapshot list:

   ```bash
   cd /opt/shadow && sudo scripts/ops/backup-offsite.sh
   sudo scripts/ops/restic.sh snapshots
   ```

8. Also keep `.env.production` in the password manager. Each backup carries a copy
   of it, but you need the restic password first to read it, so the password must
   also be somewhere other than the host (step 4).

For the beta change `OnCalendar` in `shadow-backup.timer` to `hourly` (and the
heartbeat period to 1 hour, grace 2 hours), then
`sudo systemctl daemon-reload && sudo systemctl restart shadow-backup.timer`.

## Rehearse a restore

Do this once before the alpha and then quarterly, and write the date, the time it
took, and the result next to the alpha or beta gate.

1. On any machine with Docker and the repository (for example the host itself
   against scratch databases):

   ```bash
   cd /opt/shadow && sudo DRILL=1 scripts/ops/restore-offsite.sh /tmp/restore
   ```

   This restores the newest snapshot and runs `restore-drill.sh`, which loads each
   dump into a scratch database, prints the schema revision and counts, and drops
   it. Production data is untouched.
2. Before the beta also rehearse the hard case on a **new empty host**: install
   Docker and restic, fetch the repository password from the password manager,
   put the `BACKUP_SCW_*` and `RESTIC_PASSWORD` values in the environment (the file
   does not exist there yet), restore the latest snapshot (`restore-offsite.sh`),
   take `.env.production` from the restored files, start `db` with `docker compose -f docker-compose.prod.yml up -d db`,
   load both dumps with `pg_restore --clean --if-exists --no-owner` (Shadow
   dump into the Shadow database as the Shadow owner, Authentik dump into the
   Authentik database as the Authentik owner), start the stack, sign in, and open a
   Shadow. Time it.

## Restore into production

1. Stop the application: `docker compose -f docker-compose.prod.yml stop backend worker authentik-server authentik-worker`.
2. Restore the snapshot into a directory with `scripts/ops/restore-offsite.sh`.
3. Load each dump with `pg_restore --clean --if-exists --no-owner --role=<owner> -d <database>`
   inside the `db` container (see `restore-drill.sh` for the exact form).
4. Start the stack and check `/health` and the monitoring endpoint.

## Alerts

- **Email (default).** `scripts/ops/notify-email.sh` calls the Scaleway Transactional
  Email API the way the application does (`SCW_SECRET_KEY`, `SCW_DEFAULT_PROJECT_ID`,
  `SCW_TEM_*`, all already in `.env.production`) and sends to `BACKUP_ALERT_EMAIL`.
  Nothing leaves your own Scaleway account. It reports a failed backup, an optional
  success report, and a disk above `DISK_MAX_PERCENT` (at most one email per six
  hours). It cannot report that the host itself is down or the timer never fired;
  the daily success email makes that visible by its absence, and the uptime check
  covers a dead host.
- **Heartbeat (optional).** `BACKUP_HEARTBEAT_URL` and `DISK_HEARTBEAT_URL` make the
  scripts send an outgoing HTTPS request to a monitoring service you choose
  (Healthchecks and similar) on success and to `/fail` on failure; the service
  alerts when the request stops coming. The service never connects to the host, and
  the request carries no data. Leave both empty to use no external service.

## Operating

- A failure email, or a missing daily success email, means no recent backup: look at
  `journalctl -u shadow-backup`.
- Take a backup (`sudo systemctl start shadow-backup`) before each deploy;
  migrations run automatically.
- Rotate the bucket key by creating a new one, updating `BACKUP_SCW_ACCESS_KEY` and `BACKUP_SCW_SECRET_KEY` in `.env.production`, and deleting
  the old one. Never change the restic password without keeping the old one until
  every snapshot written with it has been pruned.
