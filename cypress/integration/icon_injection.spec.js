describe('Icon injection', () => {
  it('Icon Rendering Test - postgres (file assertions)', () => {
    cy.readFile('cypress/fixtures/diagram_postgres.html').then((html) => {
      expect(html).to.include('symbol id="icon-postgres"');
      expect(html).to.include('g id="node-1"');
      expect(html).to.include('use href="#icon-postgres"');
    });
  });

  it('Multi-Icon Test - postgres+kafka+minio (file assertions)', () => {
    cy.readFile('cypress/fixtures/diagram_multi.html').then((html) => {
      expect(html).to.include('symbol id="icon-postgres"');
      expect(html).to.include('symbol id="icon-kafka"');
      expect(html).to.include('symbol id="icon-minio"');
      // ensure three injected markers
      const matches = (html.match(/data-icon-injected="1"/g) || []);
      expect(matches.length).to.eq(3);
    });
  });

  it('Unknown service does not inject unknown symbol and falls back to generic', () => {
    cy.readFile('cypress/fixtures/diagram_unknown.html').then((html) => {
      expect(html).to.not.include('symbol id="icon-unknown-service"');
      expect(html).to.include('symbol id="icon-service-generic"');
      expect(html).to.include('use href="#icon-service-generic"');
    });
  });
});
