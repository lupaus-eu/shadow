---
status: accepted
---

# Use Scaleway Transactional Email

Scaleway Transactional Email sends all identity and application-generated transactional email. Authentik uses SMTP with STARTTLS for verification and recovery, while Yearclock uses the REST API behind a PostgreSQL outbox worker. The two services use separate IAM credentials and sender identities, and production requires verified SPF, DKIM, DMARC, and MX configuration.
