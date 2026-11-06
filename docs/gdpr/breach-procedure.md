# Personal data breach procedure (GDPR Articles 33 and 34)

Owner: Platform Operator (the named person is `TODO(operator)`)  
Review by: 2027-05-05, then every six months and after any change to the data the product keeps  
Status: draft for counsel. An engineering record, not legal advice. It holds no personal data and no incident details.

A person is named for each role before launch: **Incident lead** `TODO(operator)` and **Deputy** `TODO(operator)`.
The register itself lives outside git (see [private-registers.md](private-registers.md)).

## Steps

1. **Contain.** Stop the cause (revoke a key or session, block access, take the service read-only) and keep evidence.
   Secrets are rotated as described in `docs/runbooks/production-readiness.md`.
2. **Record.** Open a register entry at once: when it was found, by whom, what happened, which Organizations are affected.
3. **Assess.** Is personal data affected, and is there a risk to the people? Use what the database and Audit Log show
   (never an Organization's content unless Support Access was approved).
4. **Tell controllers (as processor, Article 33(2)).** Where the breach concerns planning content, tell each affected
   customer's Owners without undue delay `TODO(lawyer)` the number of hours promised in the data processing agreement.
5. **Tell the authority (as controller, Article 33(1)).** Where the breach concerns data Yearclock controls and risk is
   likely, notify the Data Protection Ombudsman (tietosuojavaltuutettu) within 72 hours of becoming aware, in stages if
   the facts are incomplete.
6. **Tell the people (Article 34)** when the risk is high, in plain language.
7. **Close and learn.** Record the cause, the effect, the fix, and what changes in the code or the runbooks.

Every breach is documented in the register, including those not notified (Article 33(5)).
