import { Card } from '@/components/ui';

/** The two screens still to be built, in P8. The admin placeholders these sat
 *  beside were replaced by real screens in P7. */
function Placeholder({ title, phase }: { title: string; phase: string }) {
  return (
    <Card title={title}>
      <p className="text-sm text-ink-500">
        Not built yet — scheduled for {phase}.
      </p>
    </Card>
  );
}


export const StudentEvaluate = () => <Placeholder title="Give feedback" phase="P8" />;
export const FacultyResults = () => <Placeholder title="My results" phase="P8" />;

export const NotFound = () => (
  <Card title="Page not found">
    <p className="text-sm text-ink-500">
      That page does not exist, or you do not have access to it.
    </p>
  </Card>
);
