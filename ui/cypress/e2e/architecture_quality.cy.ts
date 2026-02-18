describe('Architecture Quality API via UI tests', () => {
  const apiUrl = Cypress.env('ARCH_QUALITY_URL') || 'http://localhost:8000/api/analysis/architecture-quality'

  it('returns a structured report for a simple cyclic IR', () => {
    const ir = {
      nodes: [{ id: 'A' }, { id: 'B' }, { id: 'C' }],
      edges: [
        { source: 'A', target: 'B' },
        { source: 'B', target: 'C' },
        { source: 'C', target: 'A' },
      ],
    }

    cy.request({ method: 'POST', url: apiUrl, body: { ir }, failOnStatusCode: false }).then((resp) => {
      expect(resp.status).to.be.oneOf([200, 201])
      expect(resp.body).to.have.property('score')
      expect(resp.body).to.have.property('issues')
      const issues = resp.body.issues || []
      const hasCycle = issues.some((i: any) => i.id === 'CYCLE_DETECTED')
      expect(hasCycle).to.be.true
    })
  })
})
