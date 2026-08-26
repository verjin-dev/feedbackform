# Faculty Evaluation

Students give anonymous feedback on the teaching they receive; faculty read what
their classes said; administrators run the term and produce the returns an
accreditor asks for.

This replaces a PHP application that had been in production at the college for
several years. That application is in [`archive/`](archive/), still runnable, and
is the reference for anything this system is expected to reproduce.

---

## Layout

| Path | What it is |
| --- | --- |
| [`backend/`](backend/) | FastAPI + PostgreSQL. The API, the migrations, and the tooling that imports the legacy database. |
| [`frontend/`](frontend/) | React + TypeScript. Every screen, for all three roles. |
| [`deploy/`](deploy/) | nginx, systemd, an annotated environment file, and [`CUTOVER.md`](deploy/CUTOVER.md) — the runbook for going live. |
| [`archive/`](archive/) | The legacy PHP application, with the security fixes described below applied. |

---

## Running it

You need Python 3.12, Node 20+, and a PostgreSQL database.

Paths below use `.venv/bin` (macOS, Linux). On Windows the same commands live
under `.venv/Scripts`.

**Backend**

```bash
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Copy `deploy/api.env.example` to `backend/.env` and set at least `DATABASE_URL`
and `SECRET_KEY`. There is deliberately no default for either: the application
this replaces kept database credentials in a committed file, and this one
refuses to start rather than falling back to something that happens to work.

```bash
cd backend && .venv/bin/alembic upgrade head
```

```bash
cd backend && .venv/bin/uvicorn app.main:app --reload
```

**Frontend**

```bash
cd frontend && npm install && npm run dev
```

The dev server proxies `/api` to the backend so both halves share an origin.
That is not a convenience — the session cookie is `SameSite=Lax`, so a
cross-origin setup would silently fail to authenticate. Production does the same
thing through nginx.

**Tests**

```bash
cd backend && .venv/bin/pytest
```

```bash
cd frontend && npm test
```

451 backend tests and 59 frontend tests. Both suites run in a couple of minutes
and are expected to be green before anything is committed.

---

## The parts that are decisions, not implementation

Most of this is an ordinary CRUD application. These are the places where it
deliberately does something other than the obvious thing, and where a change
made without reading first will break something that matters.

### Anonymity is structural, not a policy

Two tables, never joined. `EvaluationSubmission` records **that** a student took
part, so nobody is asked twice and response rates can be reported.
`EvaluationResponse` holds **what** was said. Nothing links them — not a foreign
key, not a shared identifier, not a timestamp precise enough to correlate.

The legacy application stored the student id on the rating row. Anonymity was a
promise made on a screen and contradicted by the schema.

The audit log ([`app/services/audit.py`](backend/app/services/audit.py)) is
covered by the same rule and says so at length: it records configuration and
access, never submissions, comment text, or anything about the mid-term pulse.
An administrator who could read "student 41 submitted at 14:02" would have been
handed, in a different table, exactly what this design removes.

### Small samples are reported as small samples

No mean is published below five responses; the distribution is shown instead. A
mean drawn from a minority of the class is published and flagged. Every
published mean carries a 95% interval, clamped to the 1–5 scale, because with
six responses the width of that interval makes the point on its own.

The legacy report divided each tally by an unchecked count and omitted questions
nobody had answered, so a barely-answered questionnaire rendered as a complete
one.

### Questions can belong to a department

A question with no curriculum is asked of everybody; one with a curriculum is
asked only of students whose class carries it. The consequence that matters is
in the report: it is shaped per department, so another department's question is
**absent** rather than present with counts of zero — on the page those two look
identical, and only one of them is true.

### Tamil falls back, never disappears

Interface strings ship with the application. Question wording belongs to the
college and is entered per question. A question with no Tamil is shown to Tamil
readers in English and is still asked, because a half-translated questionnaire is
readable while one that drops its untranslated questions is quietly a different
questionnaire.

**The Tamil in this repository has not been reviewed by a Tamil speaker.** See
the checklist in [`CUTOVER.md`](deploy/CUTOVER.md) before it goes in front of
students.

### College sign-in matches, never creates

Optional, off until configured, and staff only. It signs in an account an
administrator already created; it never creates one. The link is keyed on the
identity provider's subject identifier rather than on the email address, because
addresses get reassigned when somebody leaves — matching on the address would
hand their successor their account.

Password sign-in keeps working, permanently. An identity-provider outage during
an evaluation window would otherwise lock the college out of its own feedback in
the one week it cannot wait.

---

## About `archive/`

The legacy application, moved here intact. It carries the interim security work
done before the rebuild started, on the assumption it would have to keep running
in the meantime:

- Login was `"SELECT * FROM {$table} WHERE ..."` with an unvalidated table name
  chosen by a form field. `' OR 1=1 -- ` signed you in as an administrator with
  no password. Parameterised, with the role index validated.
- `ajax.php` dispatched thirty actions with no permission check at all.
  Replaced with an allowlist checked per role before anything is constructed.
- `update_user` took the row id from the POST body and copied every POST key
  into the session. One request as one student changed another student's name
  and password and moved the session onto their account. Demonstrated against
  the running application, then fixed.
- Role folders had no guard beyond the folder name. Guards prepended to all 45
  files.
- `index.php` emitted a doctype before `session_start()`, so whether
  authentication worked at all depended on `output_buffering`.

> **This hardening has not been deployed.** It is committed here and verified
> against PHP 8.3 and MariaDB 10.11, but the server running at the college is
> still on the code from before it. That is the most urgent item in this
> repository.

The pre-rework history is preserved under the `archive/pre-rework` tag.

---

## Where to look next

- [`deploy/CUTOVER.md`](deploy/CUTOVER.md) — going live, rehearsing it, and
  rolling back. Read this before touching production.
- [`backend/etl/`](backend/etl/) — importing the legacy database and reconciling
  the result against it.
- [`backend/app/services/reporting.py`](backend/app/services/reporting.py) — the
  aggregation the faculty report, the admin report and the accreditation export
  all share. Two implementations of this arithmetic would eventually disagree,
  and a document submitted to an accreditor that does not match the screen it
  was checked against is the worst version of that problem.
