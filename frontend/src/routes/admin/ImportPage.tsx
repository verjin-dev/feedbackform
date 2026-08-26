import { useMutation } from '@tanstack/react-query';
import { useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';

import { ApiError } from '@/api/client';
import { Badge, DataTable } from '@/components/DataTable';
import { Alert, Button, Card, cx } from '@/components/ui';

interface ImportRow {
  line: number;
  action: 'create' | 'update' | 'skip' | 'error';
  email: string;
  name: string;
  role: string;
  messages: string[];
  generated_password: string | null;
}

interface ImportReport {
  dry_run: boolean;
  file_errors: string[];
  total: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  ok: boolean;
  rows: ImportRow[];
}

const TONES = {
  create: 'positive',
  update: 'caution',
  skip: 'neutral',
  error: 'critical',
} as const;

const SAMPLE = `role,first_name,last_name,email,school_id,curriculum,level,section
student,Nila,Suresh,nila.suresh@example.edu,S2301,B.E. CSE,III,A
faculty,Ravi,Kumar,ravi.kumar@example.edu,F1042,,,`;

/**
 * CSV upload with a compulsory preview.
 *
 * The upload is always run as a dry run first and the result shown in full;
 * writing is a second, deliberate action. It is not possible to import a file
 * from this screen without having seen what it will do.
 */
export function ImportPage() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [onExisting, setOnExisting] = useState<'skip' | 'update'>('skip');
  const [preview, setPreview] = useState<ImportReport | null>(null);
  const [committed, setCommitted] = useState<ImportReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: async ({ dryRun }: { dryRun: boolean }) => {
      if (file === null) throw new Error('Choose a file first.');
      const body = new FormData();
      body.append('file', file);
      const response = await fetch(
        `/api/accounts/import?dry_run=${dryRun}&on_existing=${onExisting}`,
        { method: 'POST', body, credentials: 'same-origin' },
      );
      const text = await response.text();
      const parsed: unknown = text ? JSON.parse(text) : null;
      if (!response.ok) {
        const detail =
          typeof parsed === 'object' && parsed !== null && 'detail' in parsed
            ? String((parsed as { detail: unknown }).detail)
            : `Import failed (${response.status})`;
        throw new ApiError(response.status, detail, parsed);
      }
      return parsed as ImportReport;
    },
  });

  function reset() {
    setPreview(null);
    setCommitted(null);
    setError(null);
  }

  async function run(dryRun: boolean) {
    setError(null);
    try {
      const report = await send.mutateAsync({ dryRun });
      if (dryRun) {
        setPreview(report);
        setCommitted(null);
      } else {
        setCommitted(report);
        setPreview(null);
        // New accounts change every list and every response-rate denominator.
        void queryClient.invalidateQueries();
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Import failed.');
    }
  }

  const report = committed ?? preview;
  const createdWithPasswords =
    committed?.rows.filter((row) => row.generated_password) ?? [];

  return (
    <div className="flex flex-col gap-4">
      {error ? <Alert>{error}</Alert> : null}

      <Card title="Import accounts from a spreadsheet">
        <div className="flex flex-col gap-4">
          <p className="max-w-prose text-sm text-ink-500">
            Upload a CSV to add students, faculty or administrators in bulk. The
            file is checked and previewed first — nothing is written until you
            confirm.
          </p>

          <div className="flex flex-wrap items-end gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-ink-700">CSV file</span>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                  reset();
                }}
                className="text-sm text-ink-600 file:mr-3 file:rounded-md file:border-0 file:bg-ink-100 file:px-3 file:py-2 file:text-sm file:text-ink-700"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-sm font-medium text-ink-700">
                If an account already exists
              </span>
              <select
                value={onExisting}
                onChange={(event) => {
                  setOnExisting(event.target.value as 'skip' | 'update');
                  reset();
                }}
                className="rounded-md bg-white px-3 py-2 text-sm text-ink-800 ring-1 ring-ink-200"
              >
                <option value="skip">Leave it unchanged</option>
                <option value="update">Update its name and class</option>
              </select>
            </label>

            <Button
              onClick={() => void run(true)}
              disabled={file === null}
              loading={send.isPending && preview === null && committed === null}
            >
              Check file
            </Button>
          </div>

          <details className="text-sm text-ink-500">
            <summary className="cursor-pointer">What the file should contain</summary>
            <div className="mt-2 flex flex-col gap-2">
              <p>
                A header row and one row per person. Students need{' '}
                <code className="rounded bg-ink-100 px-1">curriculum</code>,{' '}
                <code className="rounded bg-ink-100 px-1">level</code> and{' '}
                <code className="rounded bg-ink-100 px-1">section</code> matching a
                class that already exists. Leave{' '}
                <code className="rounded bg-ink-100 px-1">password</code> out and one
                will be generated for each person.
              </p>
              <pre className="overflow-x-auto rounded-md bg-ink-50 p-3 text-xs text-ink-700">
                {SAMPLE}
              </pre>
            </div>
          </details>
        </div>
      </Card>

      {report?.file_errors.length ? (
        <Alert>
          <div className="flex flex-col gap-1">
            {report.file_errors.map((message) => (
              <span key={message}>{message}</span>
            ))}
          </div>
        </Alert>
      ) : null}

      {report && report.file_errors.length === 0 ? (
        <Card
          title={committed ? 'Imported' : 'Preview'}
          actions={
            committed ? null : (
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={reset}>
                  Cancel
                </Button>
                <Button
                  onClick={() => void run(false)}
                  loading={send.isPending}
                  disabled={!report.ok || report.created + report.updated === 0}
                  title={
                    report.ok
                      ? undefined
                      : 'Fix the rows marked below before importing.'
                  }
                >
                  Import {report.created + report.updated} account
                  {report.created + report.updated === 1 ? '' : 's'}
                </Button>
              </div>
            )
          }
        >
          <div className="mb-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <Summary label={committed ? 'Created' : 'To create'} value={report.created} />
            <Summary label={committed ? 'Updated' : 'To update'} value={report.updated} />
            <Summary label="Left unchanged" value={report.skipped} />
            <Summary label="Problems" value={report.errors} critical />
          </div>

          {!report.ok && !committed ? (
            <div className="mb-4">
              <Alert>
                Nothing will be imported while any row has a problem. Fix the rows
                below and upload again — a partly imported roll is worse than none,
                because the missing people are invisible until their response rates
                look wrong.
              </Alert>
            </div>
          ) : null}

          {createdWithPasswords.length > 0 ? (
            <div className="mb-4">
              <Alert tone="caution">
                Passwords were generated for {createdWithPasswords.length} new
                account{createdWithPasswords.length === 1 ? '' : 's'}. They are shown
                below <strong>once</strong> — copy them now and give them to the
                people concerned.
              </Alert>
            </div>
          ) : null}

          <DataTable
            rows={report.rows}
            rowKey={(row) => row.line}
            columns={[
              { header: 'Line', cell: (row) => row.line, numeric: true, width: '4rem' },
              {
                header: 'Action',
                cell: (row) => <Badge tone={TONES[row.action]}>{row.action}</Badge>,
              },
              { header: 'Name', cell: (row) => row.name || '—' },
              { header: 'Email', cell: (row) => row.email || '—' },
              { header: 'Role', cell: (row) => row.role || '—' },
              {
                header: committed ? 'Password / notes' : 'Notes',
                cell: (row) => (
                  <div className="flex flex-col gap-1">
                    {row.generated_password ? (
                      <code className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">
                        {row.generated_password}
                      </code>
                    ) : null}
                    {row.messages.map((message) => (
                      <span
                        key={message}
                        className={cx(
                          'text-xs',
                          row.action === 'error' ? 'text-critical-600' : 'text-ink-500',
                        )}
                      >
                        {message}
                      </span>
                    ))}
                  </div>
                ),
              },
            ]}
          />
        </Card>
      ) : null}
    </div>
  );
}

function Summary({
  label,
  value,
  critical = false,
}: {
  label: string;
  value: number;
  critical?: boolean;
}) {
  return (
    <div>
      <div className="text-xs uppercase text-ink-500">{label}</div>
      <div
        className={cx(
          'text-xl font-semibold tabular-nums',
          critical && value > 0 ? 'text-critical-600' : 'text-ink-900',
        )}
      >
        {value}
      </div>
    </div>
  );
}
