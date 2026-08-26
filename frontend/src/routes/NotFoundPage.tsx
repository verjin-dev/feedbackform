import { Card } from '@/components/ui';

export function NotFoundPage() {
  return (
    <Card title="Page not found">
      <p className="text-sm text-muted">
        That page does not exist, or you do not have access to it.
      </p>
    </Card>
  );
}
