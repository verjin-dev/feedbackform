# Cutover runbook

Replacing the PHP application with the React and FastAPI rebuild.

**Schedule this between terms** — after one term's results are pulled and
before the next term's assignments are configured. Cutting during an open
evaluation window risks losing submissions students cannot be asked to repeat.

Two things this runbook assumes you have, and which nothing in the repository
can supply:

1. **A behaviour reference for the live app** (P0). Walk every screen on the
   current system and record what it does — especially the report percentages
   for two or three real faculty members. Without it there is nothing to
   reconcile against, and "the numbers look about right" is not a check.
2. **A maintenance window agreed with the college**, long enough for the
   import plus verification. For a few thousand evaluations the import itself
   is minutes; the verification is what takes the time.

---

## Before the day

- [ ] **Deploy P1 hardening to the live PHP app** if it is still not deployed.
      It is independent of everything here and should not wait for cutover.
- [ ] Provision the server: Postgres 16, Python 3.12, nginx, a TLS certificate.
- [ ] Create the `evaluation` system user and `/srv/evaluation`.
- [ ] Rehearse this entire runbook against a **copy** of production. The first
      time you run the import must not be the day you need it to work.
- [ ] Time the rehearsal. That number is what you tell the college.

### Rehearsal, in full

```bash
# 1. Copy production, do not touch production.
mysqldump -u root -p evaluation_db > legacy_$(date +%F).sql
mysql -u root -p -e "CREATE DATABASE evaluation_rehearsal"
mysql -u root -p evaluation_rehearsal < legacy_$(date +%F).sql

# 2. Find out what the new schema will refuse. Writes nothing.
cd /srv/evaluation/backend && source .venv/bin/activate
python -m etl.import_legacy analyse \
    --legacy "mysql+pymysql://root:PASSWORD@127.0.0.1/evaluation_rehearsal"
```

Work through every **BLOCKER** before going further. Each one is data the new
schema cannot hold:

| Finding | What it means | What to do |
|---|---|---|
| `duplicate-email` | The same address is in two of `users`, `faculty_list`, `student_list` | Decide which account is real; change or delete the other in the legacy database |
| `duplicate-school-id` | Two accounts share a roll or staff number | Correct one |
| `student-without-class` | A student's class was deleted | Reassign them, or delete the account if they have left |
| `rating-out-of-range` | Ratings outside 1–5 exist | Correct or delete those `evaluation_answers` rows |
| `blank-email` | An account has no address | Give it one; it is the login identifier |
| `duplicate-term` | Same year and semester twice | Merge them |

**WARNING** findings do not block, but each one loses something. Read them and
decide deliberately — particularly `duplicate-submission`, which changes
reported percentages, and `orphan-evaluation`, which drops feedback whose
assignment no longer exists.

The `anonymity` note is **one-way**: after import, no rating can be traced back
to the student who gave it. That is the point of the redesign, and there is no
undo short of restoring the legacy database.

---

## Cutover day

### 1. Freeze and back up

```bash
# Take the PHP app offline so nothing is written while you copy it.
sudo systemctl stop apache2

mysqldump -u root -p evaluation_db > /srv/backups/legacy_final_$(date +%F_%H%M).sql
# Verify the dump is not truncated before relying on it.
tail -5 /srv/backups/legacy_final_*.sql   # expect "Dump completed"
```

- [ ] Dump taken, size sane, `Dump completed` present
- [ ] Dump copied **off the machine**

### 2. Create the target database

```bash
sudo -u postgres createuser evaluation --pwprompt
sudo -u postgres createdb evaluation --owner evaluation

cd /srv/evaluation/backend && source .venv/bin/activate
export $(grep -v '^#' /etc/evaluation/api.env | xargs)
alembic upgrade head
alembic check          # expect "No new upgrade operations detected."
```

### 3. Import

```bash
python -m etl.import_legacy analyse --legacy "mysql+pymysql://root:PASSWORD@127.0.0.1/evaluation_db"
python -m etl.import_legacy import  --legacy "mysql+pymysql://root:PASSWORD@127.0.0.1/evaluation_db"
```

The import refuses to run while blockers stand. `--force` skips the offending
rows instead — only use it if you have read every blocker and accepted the
loss.

- [ ] Import completed; the created/skipped counts match the rehearsal

### 4. Reconcile

```bash
python -m etl.reconcile --legacy "mysql+pymysql://root:PASSWORD@127.0.0.1/evaluation_db"
```

Row counts for questions, students, assignments and submissions are *expected*
to be lower — orphans and duplicates were dropped. What must not move is the
**per-question means**, and `submissions vs responses` must be exactly equal:
response rates are computed from one and ratings hang off the other.

- [ ] No `FAIL` lines
- [ ] Spot-check two faculty reports against the P0 reference by eye

### 5. Rotate credentials

- [ ] `SECRET_KEY` in `/etc/evaluation/api.env` is freshly generated, not the example
- [ ] The Postgres password is not the one used in rehearsal
- [ ] **Any account still using the shipped `admin123` password has been changed** —
      it is a publicly known hash and survives the import as a legacy hash

### 6. Start and switch

```bash
sudo cp deploy/evaluation-api.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now evaluation-api
curl -s localhost:8000/health          # {"status":"ok","environment":"production"}

cd /srv/evaluation/frontend-src && npm ci && npm run build
sudo rsync -a --delete dist/ /srv/evaluation/frontend/

sudo cp deploy/nginx.conf /etc/nginx/sites-available/evaluation
sudo ln -sf /etc/nginx/sites-available/evaluation /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 7. Verify on the real domain

- [ ] Sign in as an admin, a faculty member and a student — **each with their
      original password**, proving the MD5 upgrade path works
- [ ] Confirm the same accounts can sign in a second time (they are Argon2 now)
- [ ] A faculty member sees their own results and gets 403 for another's
- [ ] A student sees only their class's subjects
- [ ] Open the site on a phone and complete one evaluation end to end
- [ ] `document.cookie` is empty in the browser console — the session is httpOnly

### 8. Close out

- [ ] Leave the PHP vhost **disabled but restorable** for two weeks
- [ ] Announce to students and faculty
- [ ] Diarise the forced-reset sweep at 30 days:
      `SELECT id, email FROM account WHERE legacy_md5 IS NOT NULL;`
- [ ] After one clean term, archive and remove the PHP app

---

## Before Tamil goes in front of students

The interface strings in `frontend/src/i18n/strings.ts` and the two comment
prompts in `backend/app/core/i18n.py` were written by the tooling that built
this, not by a Tamil speaker at the college. They are readable, not authorised.

- [ ] A Tamil speaker on staff reads both files end to end
- [ ] Someone decides whether the register is right for first-year students —
      the drafts use the polite plural throughout
- [ ] The rating words in particular are checked: `rating.1`–`rating.5` carry
      the whole meaning of the scale, and a student who reads "மோசம்" as
      harsher than "Poor" will rate differently

Question wording is separate and is the college's own. It is entered per
question on the questionnaire screen and is never translated by the
application. Questions with no Tamil are marked **No Tamil** on that screen and
appear to Tamil readers in English — they are still asked, because a
half-translated questionnaire is readable while one that drops its
untranslated questions is quietly a different questionnaire.

- [ ] Decide whether to launch Tamil with a partly translated questionnaire or
      wait for a full one. Either works; only the second needs a deadline.

---

## Rollback

Decide this before you need it. Rollback is cheap for the first two weeks and
expensive afterwards, because **evaluations submitted on the new system do not
exist in the legacy database** — going back loses them.

**Trigger it if:** reconciliation fails and cannot be explained; sign-in does
not work for a role; reports show numbers you cannot account for.

```bash
sudo systemctl stop evaluation-api
sudo rm /etc/nginx/sites-enabled/evaluation
sudo systemctl start apache2          # PHP app returns
sudo systemctl reload nginx
```

The legacy database was never modified by the import — it is only read — so the
old app comes back to exactly the state it was frozen in.

- [ ] Rollback rehearsed and **timed** at least once
- [ ] Everyone who might need to run it knows where this file is

After the first student submits on the new system, rolling back means exporting
those submissions and re-entering them by hand. Set a date at which rollback is
formally off the table, and say so out loud.
