describe('GitHub ingest loading indicator', () => {
  it('shows loading while ingest job is processing and clears on completion', () => {
    const sessionId = '11111111-1111-1111-1111-111111111111';
    const jobId = '22222222-2222-2222-2222-222222222222';

    cy.intercept('POST', '/api/sessions', {
      statusCode: 200,
      body: { session_id: sessionId, title: 'Architecture Session' },
    }).as('createSession');

    cy.intercept('POST', '/api/ingest', {
      statusCode: 202,
      body: { job_id: jobId, session_id: sessionId, status: 'queued', result: null, error: null },
    }).as('enqueueIngest');

    let pollCount = 0;
    cy.intercept('GET', `/api/ingest/${jobId}`, (req) => {
      pollCount += 1;
      const status = pollCount < 2 ? 'processing' : 'complete';
      req.reply({
        statusCode: 200,
        body: {
          job_id: jobId,
          session_id: sessionId,
          status,
          result: status === 'complete' ? { diagrams: [] } : null,
          error: null,
        },
      });
    }).as('pollIngest');

    cy.intercept('GET', `/api/sessions/${sessionId}`, {
      statusCode: 200,
      body: {
        session_id: sessionId,
        title: 'Architecture Session',
        source_repo: null,
        source_commit: null,
        plan: null,
        plans: [],
        messages: [],
        images: [],
        diagrams: [],
      },
    }).as('refreshSession');

    cy.visit('/');
    cy.get('[data-cy="chat-input"]').type('https://github.com/org/repo');
    cy.get('[data-cy="send-button"]').click();

    cy.contains('Analyzing repository…').should('be.visible');
    cy.wait('@enqueueIngest');
    cy.wait('@pollIngest');
    cy.wait('@pollIngest');
    cy.wait('@refreshSession');
    cy.contains('Analyzing repository…').should('not.exist');
  });
});
