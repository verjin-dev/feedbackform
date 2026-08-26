import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '@/api/client';
import { Badge } from '@/components/DataTable';
import { Card } from '@/components/ui';

interface AuditEvent {
  id: number;
  at: string;
  actor_email: string;
  actor_name: string;
  action: 'created' | 'updated' | 'deleted';
  entity_type: string;
  entity_id: string;
  summary: string;
  changes: string | null;
}

const ACTION_TONE = {
  created: 'positive',
  updated: 'caution',
  deleted: 'critical',
} as const;

/** "status: 'open' -> 'closed'" as two readable halves. */
function Change({ line }: { line: string }) {
  const [field, rest] = line.split(/:\s(.+)/);
  return (
    <div className="flex flex-wrap gap-x-2 text-xs">
      <span className="font-medium text-ink-600">{field}</span>
      <span className="text-ink-500">{rest}</span>
    </div>
  );
}

/**
 * Configuration and access changes.
 *
 * Deliberately holds nothing about who submitted an evaluation or what they
 * wrote. This answers "did somebody change the questionnaire halfway through?",
 * not "who said that?" — and the page says so, because an audit log people
 * assume is watching them changes what they are willing to write.
 */
export function AuditPage() {
  const [entityType, setEntityType] = useState('');

  const types = useQuery({
    queryKey: ['audit', 'types'],
    queryFn: () => api.get<string[]>('/audit/entity-types'),
  });

  const events = useQuery({
    queryKey: ['audit', entityType],
    queryFn: () =>
      api.get<AuditEvent[]>('/audit', entityType ? { entity_type: entityType } : undefined),
  });

  const rows = events.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <Card
        title="Change log"
        actions={
          <label className="flex items-center gap-2 text-sm text-ink-600">
            <span>Show</span>
            <select
              value={entityType}
              onChange={(event) => setEntityType(event.target.value)}
              className="rounded-md bg-white px-2 py-1.5 text-sm text-ink-800 ring-1 ring-ink-200"
            >
              <option value="">Everything</option>
              {types.data?.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
          </label>
        }
      >
        <p className="mb-4 max-w-prose text-sm text-ink-500">
          Who changed the questionnaire, the assignments, the accounts, or the
          state of an evaluation window — and when.
        </p>

        <p className="max-w-prose rounded-md bg-positive-100 px-3 py-2 text-sm text-positive-600">
          This log records configuration, not participation. It holds nothing
          about who submitted feedback or what they wrote, by design.
        </p>

        <div className="mt-4">
          {events.isLoading ? (
            <p className="py-6 text-center text-sm text-ink-400" role="status">
              Loading...
            </p>
          ) : rows.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-400">
              Nothing recorded yet.
            </p>
          ) : (
            <ol className="flex flex-col">
              {rows.map((event) => (
                <li
                  key={event.id}
                  className="flex flex-col gap-1 border-b border-ink-100 py-3 last:border-0"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge tone={ACTION_TONE[event.action]}>{event.action}</Badge>
                    <span className="text-sm text-ink-800">{event.summary}</span>
                  </div>

                  <div className="flex flex-wrap gap-x-2 text-xs text-ink-400">
                    <span>{event.actor_name}</span>
                    <span>·</span>
                    <span>{event.actor_email}</span>
                    <span>·</span>
                    <time dateTime={event.at}>
                      {new Date(event.at).toLocaleString()}
                    </time>
                  </div>

                  {event.changes ? (
                    <div className="mt-1 flex flex-col gap-0.5 rounded-md bg-ink-50 px-3 py-2">
                      {event.changes.split('\n').map((line) => (
                        <Change key={line} line={line} />
                      ))}
                    </div>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      </Card>
    </div>
  );
}
