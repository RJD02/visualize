/**
 * BUG-BLUE-DOT regression spec — Cypress e2e
 *
 * Guards against regression of BUG-ICON-CIRCLE-RENDER-01:
 *   Regression: icon_injector produces generic blue-circle placeholders
 *   instead of real brand SVG symbols.
 *
 * These tests load the local fixture (cypress/fixtures/diagram_kafka.html)
 * so they run offline with no CDN dependencies.
 */
/* eslint-disable no-undef */

const FIXTURE = 'diagram_kafka.html';
const BLUE_CIRCLE_PATH = 'M12 2a10 10 0 100 20A10 10 0 0012 4z';
const BLUE_DOT_FILL = '#1e40af';

describe('BUG-BLUE-DOT: brand icon regression', () => {
  beforeEach(() => {
    cy.visit(`cypress/fixtures/${FIXTURE}`);
  });

  it('kafka node carries data-icon-injected="1" (server pipeline ran)', () => {
    cy.get('#kafka-node').should('have.attr', 'data-icon-injected', '1');
  });

  it('icon-kafka symbol is present in the sprite and contains path/shape elements', () => {
    cy.get('#icon-sprite #icon-kafka').should('exist');
    // The kafka symbol must have at least one real shape element (not just text)
    cy.get('#icon-sprite #icon-kafka').find('path, rect, circle, polygon, ellipse').should('exist');
  });

  it('icon-kafka symbol does NOT contain the generic blue circle path data', () => {
    cy.get('#icon-sprite #icon-kafka').then($symbol => {
      const html = $symbol.html();
      expect(html).not.to.contain(BLUE_CIRCLE_PATH);
    });
  });

  it('icon-service-generic fallback does NOT contain the blue circle path data', () => {
    cy.get('#icon-sprite #icon-service-generic').then($symbol => {
      const html = $symbol.html();
      expect(html).not.to.contain(BLUE_CIRCLE_PATH);
    });
  });

  it('no element in the diagram has fill:#1e40af (blue-dot CSS)', () => {
    cy.get('[data-cy="diagram-svg"]').then($svg => {
      const html = $svg.html();
      expect(html).not.to.contain(BLUE_DOT_FILL);
    });
  });

  it('kafka <use> references #icon-kafka (not the generic symbol)', () => {
    cy.get('#kafka-node use').should('have.attr', 'href', '#icon-kafka');
  });

  it('kafka <use> has position attributes (x, y, width, height)', () => {
    cy.get('#kafka-node use').should('have.attr', 'x');
    cy.get('#kafka-node use').should('have.attr', 'y');
    cy.get('#kafka-node use').should('have.attr', 'width');
    cy.get('#kafka-node use').should('have.attr', 'height');
  });

  it('unknown-node uses the generic symbol (not a brand-specific one)', () => {
    cy.get('#unknown-node').should('have.attr', 'data-icon-symbol', 'icon-service-generic');
    cy.get('#unknown-node use').should('have.attr', 'href', '#icon-service-generic');
  });
});
