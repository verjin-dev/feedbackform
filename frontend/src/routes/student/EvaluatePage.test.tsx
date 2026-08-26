import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EvaluatePage } from '@/routes/student/EvaluatePage';

const ASSIGNMENT = {
  assignment_id: 1,
  faculty_id: 2,
  faculty_name: 'Asha Raman',
  subject_id: 1,
  subject_code: 'CS3401',
  subject_name: 'Algorithms',
};

const QUESTIONNAIRE = {
  term: { id: 1, year: '2025-2026', semester: 1, status: 'open' },
  criteria: [
    {
      criterion_id: 1,
      name: 'Subject knowledge',
      questions: [
        { id: 10, text: 'Explains concepts clearly.' },
        { id: 11, text: 'Answers questions thoroughly.' },
      ],
    },
  ],
  comment_prompts: [
    { prompt: 'helped', text: 'What helped you learn in this subject?' },
    { prompt: 'change', text: 'What would you change?' },
  ],
};

let posted: unknown[] = [];

function stubApi({
  pending = [ASSIGNMENT],
  questionnaire = QUESTIONNAIRE,
  submitStatus = 201,
  submitBody = { assignment_id: 1, answers_recorded: 2 },
}: {
  pending?: unknown;
  questionnaire?: unknown;
  submitStatus?: number;
  submitBody?: unknown;
} = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: URL | string, init?: RequestInit) => {
      const path = url instanceof URL ? url.pathname : String(url);
      if (path.endsWith('/me/assignments/pending')) {
        return new Response(JSON.stringify(pending), { status: 200 });
      }
      if (path.endsWith('/me/questionnaire')) {
        return new Response(JSON.stringify(questionnaire), { status: 200 });
      }
      if (path.endsWith('/evaluations')) {
        posted.push(JSON.parse(String(init?.body)));
        return new Response(JSON.stringify(submitBody), { status: submitStatus });
      }
      return new Response('null', { status: 404 });
    }),
  );
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <EvaluatePage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  posted = [];
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('EvaluatePage', () => {
  it('starts with nothing selected', async () => {
    // The legacy form pre-checked 5 on every question, so a student could
    // submit a full set of top marks without reading one of them. Every rating
    // in the database was suspect as a result.
    stubApi();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).not.toBeChecked();
    }
    expect(screen.getByText('0 of 2 answered')).toBeInTheDocument();
  });

  it('refuses to submit a partial answer set and marks what is missing', async () => {
    stubApi();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const first = screen.getAllByRole('group')[0] as HTMLElement;
    await user.click(within(first).getByRole('radio', { name: /4/ }));

    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    expect(await screen.findByText(/answer every question/i)).toBeInTheDocument();
    expect(screen.getByText('Not answered')).toBeInTheDocument();
    // Nothing reached the server.
    expect(posted).toHaveLength(0);
  });

  it('submits every answer once the set is complete', async () => {
    stubApi();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const groups = screen.getAllByRole('group');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: /5/ }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: /3/ }));

    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({
      assignment_id: 1,
      ratings: [
        { question_id: 10, rating: 5 },
        { question_id: 11, rating: 3 },
      ],
      comments: [],
    });
  });

  it('states the rules before the box, not after', async () => {
    // The one safeguard on comments that is not enforced in code.
    stubApi();
    renderPage();

    await screen.findByText('What would you change?');
    expect(
      screen.getByText(/only after the feedback period closes/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/identify you to someone who was in the room/i)).toBeInTheDocument();
  });

  it('sends written feedback alongside the ratings', async () => {
    stubApi();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const groups = screen.getAllByRole('group');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: /5/ }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: /5/ }));
    await user.type(
      screen.getByRole('textbox', { name: /What would you change\?/ }),
      'More worked examples.',
    );
    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect((posted[0] as { comments: unknown[] }).comments).toEqual([
      { prompt: 'change', text: 'More worked examples.' },
    ]);
  });

  it('does not send an untouched box as an empty opinion', async () => {
    stubApi();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const groups = screen.getAllByRole('group');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: /4/ }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: /4/ }));
    await user.type(
      screen.getByRole('textbox', { name: /What would you change\?/ }),
      '   ',
    );
    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect((posted[0] as { comments: unknown[] }).comments).toEqual([]);
  });

  it('never requires written feedback to submit', async () => {
    stubApi();
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const groups = screen.getAllByRole('group');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: /3/ }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: /3/ }));
    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    await waitFor(() => expect(posted).toHaveLength(1));
  });

  it('shows the server message when a submission is rejected', async () => {
    stubApi({
      submitStatus: 409,
      submitBody: { detail: 'You have already submitted feedback for this subject.' },
    });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText('Explains concepts clearly.');
    const groups = screen.getAllByRole('group');
    await user.click(within(groups[0] as HTMLElement).getByRole('radio', { name: /5/ }));
    await user.click(within(groups[1] as HTMLElement).getByRole('radio', { name: /5/ }));
    await user.click(screen.getByRole('button', { name: 'Submit feedback' }));

    expect(
      await screen.findByText('You have already submitted feedback for this subject.'),
    ).toBeInTheDocument();
  });

  it('says the evaluation window has not opened', async () => {
    stubApi({
      questionnaire: { ...QUESTIONNAIRE, term: { ...QUESTIONNAIRE.term, status: 'pending' } },
    });
    renderPage();

    expect(await screen.findByText('Not started yet')).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('says the evaluation window has closed', async () => {
    stubApi({
      questionnaire: { ...QUESTIONNAIRE, term: { ...QUESTIONNAIRE.term, status: 'closed' } },
    });
    renderPage();

    expect(await screen.findByText('Feedback is closed')).toBeInTheDocument();
    expect(screen.queryByRole('radio')).not.toBeInTheDocument();
  });

  it('congratulates a student with nothing left to rate', async () => {
    stubApi({ pending: [] });
    renderPage();

    expect(await screen.findByText('All done')).toBeInTheDocument();
  });

  it('tells the student their answers are not attributed to them', async () => {
    // Worth stating on the page: it changes what people are willing to say,
    // and the schema was rebuilt to make it true.
    stubApi();
    renderPage();

    const mentions = await screen.findAllByText(/without your name/i);
    expect(mentions.length).toBeGreaterThan(0);
  });
});
