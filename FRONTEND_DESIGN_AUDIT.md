# LeadRescue frontend design-debt audit

**Audit date:** 2026-09-24
**Scope:** React frontend shell and its main operational views, using the local synthetic-data mode.
**Evidence:** Browser inspection of Overview, Leads, Lead detail, Follow-ups, Activity, Settings, and Privacy requests; computed-style and responsive-layout inspection at 390×844, 760×694, and 1440×900; source inventory of JSX classes and CSS selectors. No customer account or company data was used.

## Findings and changes

| Finding | Category / severity | Frequency and user impact | Status |
|---|---|---|---|
| The application stylesheet was never imported by `main.jsx`. The browser loaded zero stylesheets: body rendered with the browser-default Times font, buttons with Arial, design tokens were undefined, and the sidebar was static. | Structural / critical | Affected every user and every view; prevented the intended design system from reaching the product. | **Resolved:** `main.jsx` imports `index.css`. Browser inspection now confirms dark-theme tokens, app fonts, shell layout, cards, forms, and component styles are applied. |
| Hundreds of view-specific classes had no stylesheet selectors. Before remediation, the source scan found 287 JSX class names, only 48 CSS class selectors, and 258 unmatched names. | Implementation / critical | Affected shell, dashboard, inbox, lead detail, follow-ups, activity, settings, and shared components. | **Resolved for current source inventory:** shared and view-specific styles were added. A follow-up scan finds no unmatched static class names; remaining `Icon` and `seg-` matches are dynamic/template extraction artifacts. |
| Desktop table and mobile card forms of the inbox rendered together at narrow widths. | Structural / moderate | Confused screen-reader users and duplicated visible lead information on mobile layouts. | **Resolved:** desktop table is hidden and card list shown at widths up to 760px; desktop uses the table. |
| Global button/input resets removed native focus outlines without replacement. | Accessibility / high | Keyboard users could lose their position while navigating every screen. | **Resolved:** a visible `:focus-visible` ring is applied; keyboarding to the skip link confirmed a solid outline. |
| A remote Google Fonts import would have made typography depend on a third party. | Reliability and privacy / moderate | Affected every session, added a runtime network dependency, and sent a font request outside the application. | **Resolved:** removed the remote import; local system-font fallbacks keep rendering self-contained. |

## Browser verification

- At **1440×900**, the sidebar is sticky and 258px wide; the inbox table is displayed and the mobile card list is hidden. Dashboard, inbox, lead detail, follow-up, activity, settings, and privacy-request routes rendered with their expected headings and no document-width overflow.
- At **390×844**, the sidebar becomes a closed off-canvas navigation, the inbox switches to cards, the table is hidden, and the lead-detail columns collapse to one column. The document remains narrower than the viewport, so no horizontal page scroll is introduced.
- At the existing **760×694** browser viewport, the mobile inbox representation is selected and the page has no horizontal document overflow.
- The demo API ran locally with synthetic in-memory records only. No outbound message, CRM connection, customer data, or persistent company-data mutation was used.
- Continuation review (2026-09-24): launched the local frontend/backend in synthetic mode, seeded five in-memory example leads, and generated the new outcomes report. The observed page showed all five leads as open and no partial report state; the cohort dates and eventual-consistency/manual-value caveats were visible. No browser console errors occurred. On this view, semantic headings were H1 then H2 sections, the reporting select had a programmatic label, all buttons had accessible names, the document language was `en`, and no duplicate IDs were found. Keyboarding from the page start reached the skip link with a visible 2.4px focus outline. This was a 760×694 synthetic smoke review, not a full keyboard/screen-reader pass or WCAG audit.
- Visual screenshots can now be captured in the browser session, but prior checks still do not establish pixel-by-pixel approval across all routes and target devices.

## Remaining design and UX work

1. Conduct human visual review at common desktop, tablet, and mobile sizes; refine spacing, information density, color contrast, and data-table ergonomics based on sales-operator feedback.
2. Perform a complete keyboard and screen-reader review of menus, dialogs, filters, tables/cards, status updates, loading states, and validation. The focus-ring fix is not a WCAG conformance audit.
3. Observe representative sales users doing intake, triage, response review, follow-up, and opt-out handling. Measure time-to-first-action and task-completion errors before finalizing the information hierarchy.
4. Revisit the design after a real CRM connector is chosen; real provider fields, sync states, errors, and permissions will change the interaction model.

This audit records a major implementation defect that is now corrected. It does not certify the interface as market-leading or prove that sales teams find it usable.
